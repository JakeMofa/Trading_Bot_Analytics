"""Exact recurring trial child profiles. Legacy probe validators stay unchanged."""
from copy import deepcopy
from controller import require
from linux_actions import PROJECT,TRIAL_ORIGIN,cycle_environment
from live_profile import validate_live_profile
from structured_probe_profile import LOCAL_STAGED,OFF

WRITER_SQL={'pp_trial_history_writer_dsn':'/etc/tradebot/cloud/trial_20261119_07_history_writer_dsn',
            'pp_history_ca':'/etc/tradebot/cloud/pp_history_ca'}
WRITER_AUTH={f'trial_archive_{field}':f'/etc/tradebot/cloud/trial_20261119_07_archive_{field}'
             for field in ('api_key','email','password','uid')}


def service_name(archive):return 'sealed_archive' if archive else 'structured_probe'
def profile_name(archive):return 'trial_sealed_archive' if archive else 'trial_structured'
def overlay(archive):return 'runtime.trial-sealed-archive.compose.yaml' if archive else 'runtime.trial-structured.compose.yaml'


def child_service(base,initial_a,*,archive=False):
    service=deepcopy(base['services']['lifecycle'])
    service['environment'].pop('TRADEBOT_GENERATED_LOCAL_STORAGE',None)
    service.update(user='0:0',restart='no',profiles=[profile_name(archive)],
        command=['python','-m','postgres.pp_sealed_archive','--execute'] if archive else ['python','-m','postgres.pp_structured_service'])
    service['environment'].update(TRADEBOT_DATA_MODE='pp_live',
                                  **OFF,**cycle_environment(initial_a,TRIAL_ORIGIN))
    files=WRITER_AUTH if archive else WRITER_SQL
    if archive:
        service['environment'].update(TRADEBOT_PP_SEALED_ARCHIVE='true',
            TRADEBOT_PP_STORAGE_API_KEY_FILE='/run/secrets/trial_archive_api_key',
            TRADEBOT_PP_STORAGE_AUTH_EMAIL_FILE='/run/secrets/trial_archive_email',
            TRADEBOT_PP_STORAGE_AUTH_PASSWORD_FILE='/run/secrets/trial_archive_password',
            TRADEBOT_PP_STORAGE_AUTH_UID_FILE='/run/secrets/trial_archive_uid')
    else:
        service['environment'].update(TRADEBOT_PP_STRUCTURED_ONE_SHOT='false',TRADEBOT_PP_STRUCTURED_RECURRING='true',
            TRADEBOT_PP_SYNC_BARRIERS='true',TRADEBOT_PP_REUSE_HISTORY_SESSION='true',
            TRADEBOT_PP_RETAIN_REVISIONS='true',TRADEBOT_PP_HISTORY_DSN_FILE='/run/secrets/pp_trial_history_writer_dsn',
            TRADEBOT_PP_HISTORY_CA_FILE='/run/secrets/pp_history_ca')
    service['secrets']=[{'source':'probe_local_dsn','target':'/run/secrets/lifecycle_dsn'},
                       *({'source':name,'target':'/run/secrets/'+name} for name in files)]
    egress='raw_archive_probe_egress' if archive else 'structured_probe_egress'
    service['networks'][egress]=None
    return service


def validate_profile(base,live,actual,source,image,initial_a,*,archive=False,trial_reader=False):
    validate_live_profile(base,live,source,image,initial_a=initial_a,trial_origin=TRIAL_ORIGIN,trial_reader=trial_reader)
    expected=deepcopy(live)
    files=WRITER_AUTH if archive else WRITER_SQL
    for name,path in {**files,'probe_local_dsn':LOCAL_STAGED}.items():
        expected['secrets'][name]={'name':PROJECT+'_'+name,'file':path}
    egress='raw_archive_probe_egress' if archive else 'structured_probe_egress'
    expected['networks'][egress]={'name':PROJECT+'_'+egress,'driver':'bridge','ipam':{}}
    expected['services'][service_name(archive)]=child_service(base,initial_a,archive=archive)
    require(actual==expected,'unreviewed_trial_cloud_profile_difference')
    return actual
