"""Provides an HTTP API for mobile_app."""
import uuid
from typing import Dict

from aiohttp.web import Response, Request

from homeassistant.auth.util import generate_secret
from homeassistant.components.cloud import (async_create_cloudhook,
                                            async_remote_ui_url,
                                            CloudNotAvailable)
from homeassistant.components.http import HomeAssistantView
from homeassistant.components.http.data_validator import RequestDataValidator
from homeassistant.const import (HTTP_CREATED, CONF_WEBHOOK_ID)

from .const import (ATTR_APP_ID, ATTR_APP_NAME,
                    ATTR_DEVICE_ID, ATTR_SUPPORTS_ENCRYPTION,
                    CONF_CLOUDHOOK_URL, CONF_REMOTE_UI_URL, CONF_SECRET,
                    CONF_USER_ID, DATA_CONFIG_ENTRIES, DATA_REGISTRATIONS,
                    DOMAIN, REGISTRATION_SCHEMA)

from .device_helpers import register_device
from .helpers import supports_encryption


class RegistrationsView(HomeAssistantView):
    """A view that accepts registration requests."""

    url = '/api/mobile_app/registrations'
    name = 'api:mobile_app:register'

    @RequestDataValidator(REGISTRATION_SCHEMA)
    async def post(self, request: Request, data: Dict) -> Response:
        """Handle the POST request for registration."""
        hass = request.app['hass']

        webhook_id = generate_secret()

        if hass.components.cloud.async_active_subscription():
            data[CONF_CLOUDHOOK_URL] = \
                await async_create_cloudhook(hass, webhook_id)

        data[ATTR_DEVICE_ID] = str(uuid.uuid4()).replace("-", "")

        data[CONF_WEBHOOK_ID] = webhook_id

        if data[ATTR_SUPPORTS_ENCRYPTION] and supports_encryption():
            from nacl.secret import SecretBox

            data[CONF_SECRET] = generate_secret(SecretBox.KEY_SIZE)

        data[CONF_USER_ID] = request['hass_user'].id

        app_id = data[ATTR_APP_ID]

        if app_id in hass.data[DOMAIN][DATA_CONFIG_ENTRIES]:
            entry = hass.data[DOMAIN][DATA_CONFIG_ENTRIES][app_id]
            await register_device(hass, entry, data)
        else:
            ctx = {'source': 'registration'}
            reg_data = {
                ATTR_APP_ID: app_id,
                ATTR_APP_NAME: data[ATTR_APP_NAME]
            }
            hass.data[DOMAIN][DATA_REGISTRATIONS][webhook_id] = data
            await hass.async_create_task(
                hass.config_entries.flow.async_init(DOMAIN, context=ctx,
                                                    data=reg_data))

        remote_ui_url = None
        try:
            remote_ui_url = async_remote_ui_url(hass)
        except CloudNotAvailable:
            pass

        return self.json({
            CONF_CLOUDHOOK_URL: data.get(CONF_CLOUDHOOK_URL),
            CONF_REMOTE_UI_URL: remote_ui_url,
            CONF_SECRET: data.get(CONF_SECRET),
            CONF_WEBHOOK_ID: data[CONF_WEBHOOK_ID],
        }, status_code=HTTP_CREATED)
