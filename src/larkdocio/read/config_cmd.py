import os
import logging
from .config import get_default_config_path, new_config, read_config_from_file
from larkdocio.common import set_env_credentials, get_read_credentials, init_env
from larkdocio.common.reporting import pretty_print, check_err
from larkdocio.errors import LarkConfigError

logger = logging.getLogger("larkdocio")

def handle_config_command(app_id: str, app_secret: str, config_file: str, env_file: str = None) -> None:
    try:
        # Load env first using explicit path if provided
        init_env(env_file)

        # Decision B2: NEVER auto-write a config into the packaged
        # default (site-packages, potentially read-only). A config.json is written
        # only to an explicitly-given --config path; with no --config we read the
        # packaged default read-only.
        if config_file:
            config_path = config_file
            if not os.path.exists(config_path):
                new_config().write_to_file(config_path)
        else:
            config_path = get_default_config_path()
        logger.info(f"Working context: {config_path}")

        # Save credentials to .env if provided
        if app_id or app_secret:
            set_env_credentials(app_id, app_secret, env_file)

        # Get credentials just to display them. THIS COMMAND IS THE REMEDY the credential
        # refusal points at (`larkdocio config --appId … --appSecret …`), so it has to keep
        # running on the machine that needs it: a clone with nothing configured. Since LD-580
        # the getter refuses instead of returning blanks, so the refusal is translated back
        # into "nothing configured yet" and displayed — a remedy that cannot run where the
        # problem is would not be a remedy.
        try:
            cur_id, cur_secret = get_read_credentials()
        except LarkConfigError:
            cur_id, cur_secret = "", ""

        config = read_config_from_file(config_path)

        display_dict = config.to_dict()
        display_dict["feishu"] = {
            "app_id": cur_id,
            "app_secret": "***" if cur_secret else ""
        }

        logger.info(pretty_print(display_dict))

    except Exception as e:
        check_err(e)
