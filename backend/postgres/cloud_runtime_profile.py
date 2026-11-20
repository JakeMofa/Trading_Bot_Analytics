"""Exact cloud runtime credential targets; no inline secrets or path overrides."""
from .cloud_origin_binding import cloud_binding,LEGACY_ORIGIN,TRIAL_ORIGINS
from .rehearsal_profile import cycle_anchor


def selected_cloud_origin(environ):
    origin=environ.get('TRADEBOT_ORIGIN_ID',LEGACY_ORIGIN)
    cloud_binding(origin)
    if origin in TRIAL_ORIGINS:
        cycle_anchor(environ)
    return origin


def cloud_files(origin,*,reader=False):
    cloud_binding(origin).role(reader=reader)
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
    if origin not in TRIAL_ORIGINS: return
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
