"""Exact cloud runtime credential targets; no inline secrets or path overrides."""
from .cloud_origin_binding import BOUNDARY_ORIGIN, DISPLAY_ORIGIN, LEGACY_ORIGIN, STRUCTURED_ORIGINS, TRIAL_ORIGINS, cloud_binding
from .rehearsal_profile import cycle_anchor


def selected_cloud_origin(environ):
    origin=environ.get('TRADEBOT_ORIGIN_ID',LEGACY_ORIGIN)
    cloud_binding(origin)
    if origin in TRIAL_ORIGINS:
        cycle_anchor(environ)
    if origin in (BOUNDARY_ORIGIN, DISPLAY_ORIGIN) and (
            environ.get('TRADEBOT_PP_BOUNDARY_STRUCTURED') != 'true'
            or environ.get('TRADEBOT_PP_STRUCTURED_RECURRING') != 'true'
            or environ.get('TRADEBOT_PP_RETAIN_REVISIONS') != 'true'
            or environ.get('TRADEBOT_PP_CYCLE_INITIAL_A') is not None
            or environ.get('TRADEBOT_PP_WINDOW_POLICY') is not None):
        raise ValueError('exact boundary structured-drain profile required')
    return origin


def cloud_files(origin,*,reader=False):
    cloud_binding(origin).role(reader=reader)
    if origin in (BOUNDARY_ORIGIN, DISPLAY_ORIGIN):
        return {
            'TRADEBOT_DATABASE_DSN_FILE': '/run/secrets/lifecycle_dsn',
            'TRADEBOT_PP_HISTORY_DSN_FILE': '/run/secrets/pp_boundary_history_' + ('reader' if reader else 'writer') + '_dsn',
            'TRADEBOT_PP_HISTORY_CA_FILE': '/run/secrets/pp_history_ca',
        }
    if origin==LEGACY_ORIGIN:
        return {
            'TRADEBOT_DATABASE_DSN_FILE':'/run/secrets/lifecycle_dsn',
            'TRADEBOT_PP_HISTORY_DSN_FILE':'/run/secrets/pp_history_dsn',
            'TRADEBOT_PP_HISTORY_CA_FILE':'/run/secrets/pp_history_ca',
            'TRADEBOT_PP_STORAGE_API_KEY_FILE':'/run/secrets/history_reader_api_key' if reader else '/run/secrets/pp_storage_api_key',
            'TRADEBOT_PP_STORAGE_AUTH_EMAIL_FILE':'/run/secrets/history_reader_email' if reader else '/run/secrets/supabase_auth_email',
            'TRADEBOT_PP_STORAGE_AUTH_PASSWORD_FILE':'/run/secrets/history_reader_password' if reader else '/run/secrets/supabase_auth_password',
            'TRADEBOT_PP_STORAGE_AUTH_UID_FILE':'/run/secrets/history_reader_uid' if reader else '/run/secrets/supabase_auth_uid',
        }
    prefix='trial_history_reader' if reader else 'trial_archive'
    return {
        'TRADEBOT_DATABASE_DSN_FILE':'/run/secrets/lifecycle_dsn',
        'TRADEBOT_PP_HISTORY_DSN_FILE':'/run/secrets/pp_trial_history_reader_dsn' if reader else '/run/secrets/pp_trial_history_writer_dsn',
        'TRADEBOT_PP_HISTORY_CA_FILE':'/run/secrets/pp_history_ca',
        'TRADEBOT_PP_STORAGE_API_KEY_FILE':f'/run/secrets/{prefix}_api_key',
        'TRADEBOT_PP_STORAGE_AUTH_EMAIL_FILE':f'/run/secrets/{prefix}_email',
        'TRADEBOT_PP_STORAGE_AUTH_PASSWORD_FILE':f'/run/secrets/{prefix}_password',
        'TRADEBOT_PP_STORAGE_AUTH_UID_FILE':f'/run/secrets/{prefix}_uid',
    }


def require_trial_files(environ,origin,*,reader=False,structured=False,storage=False):
    """Legacy checks stay at their existing call sites. Trial paths are exact."""
    if origin not in STRUCTURED_ORIGINS: return
    if origin in (BOUNDARY_ORIGIN, DISPLAY_ORIGIN) and storage:
        raise ValueError('boundary diagnostic does not authorize raw Storage access')
    files=cloud_files(origin,reader=reader)
    keys=[]
    if structured: keys+=['TRADEBOT_PP_HISTORY_DSN_FILE','TRADEBOT_PP_HISTORY_CA_FILE']
    if storage: keys += [key for key in files if key.startswith('TRADEBOT_PP_STORAGE_')]
    if any(environ.get(key)!=files[key] for key in keys):
        raise ValueError('exact independent trial cloud credential paths required')
    if environ.get('TRADEBOT_PP_HISTORY_DSN'):
        raise ValueError('inline cloud credentials are forbidden')


def storage_paths(files):
    return tuple(files['TRADEBOT_PP_STORAGE_'+name+'_FILE']
                 for name in ('API_KEY','AUTH_EMAIL','AUTH_PASSWORD','AUTH_UID'))
