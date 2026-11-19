"""PP-only generated ↔ live service transition; no collector ON or cloud work.

This is an Actions component, not a public command or installed authority. A
separately reviewed root entrypoint must bind an exact CI-passed source/image,
host and one-use scope before invoking it. PostgreSQL is never recreated.
"""
from __future__ import annotations

import json
import time

from controller import DeploymentHold, require
from linux_actions import LinuxActions, SERVICES, PROJECT, history_reader_enabled, cycle_environment
from live_profile import validate_live_profile


class LiveTransition:
    def __init__(self, actions: LinuxActions, context, budget, *, initial_a=None):
        self.actions, self.context, self.budget = actions, context, budget
        self.folder = context.source / 'deploy/preprod'
        self.initial_a = initial_a
        self.cycle = cycle_environment(initial_a)

    def _compose_live(self, args, *, timeout=60):
        image = self.context.image
        require(isinstance(image,str) and image.startswith('sha256:'), 'unbound_live_image')
        overlay = ['-f',str(self.folder/'runtime.history-reader.compose.yaml')] if history_reader_enabled(self.context) else []
        env = self.actions._environment(image)
        if self.cycle:
            env.update(self.cycle)
            overlay.extend(['-f', str(self.folder/'runtime.live-cycle.compose.yaml')])
        profiles = ['--profile','migration'] if args and args[0] == 'config' else []
        return self.budget.run(['docker','compose','--env-file','/dev/null',
            '--project-name',PROJECT,'--project-directory',str(self.folder),
            '-f',str(self.folder/'compose.yaml'),
            '-f',str(self.folder/'runtime.compose.yaml'),
            '-f',str(self.folder/'runtime.live.compose.yaml'),*overlay,*profiles,*args],
            cwd=self.context.source,env=env,timeout=timeout)

    def _profile(self):
        base=self.actions._json(self.actions._compose(self.context,self.budget,
            ['config','--format','json']))
        live=self.actions._json(self._compose_live(['config','--format','json']))
        validate_live_profile(base,live,self.context.source,self.context.image,reader=history_reader_enabled(self.context),
                              initial_a=self.initial_a)

    def _live_off(self):
        # Use the lifecycle role even if operator HTTP is unavailable. Its
        # writer-row lock drains an in-flight acknowledged write before OFF.
        live=lambda args,timeout:self._compose_live(args,timeout=timeout)
        result=self.actions._json(self.actions._oneoff(self.context,self.budget,'lifecycle',
            ['python','-m','postgres.lifecycle_worker','--stop-collector'],timeout=30,compose=live))
        require(result.get('environment')=='preprod' and result.get('origin_id')=='pp-live-pp'
                and result.get('collector_enabled') is False,'pp_live_durable_off_unproven')
        status=self.actions._json(self.actions._oneoff(self.context,self.budget,'lifecycle',
            ['python','-m','postgres.lifecycle_worker','--collector-status'],timeout=30,compose=live))
        require(status.get('environment')=='preprod' and status.get('origin_id')=='pp-live-pp'
                and status.get('collector_enabled') is False,'pp_live_durable_off_unproven')

    def _check_live_off(self):
        self.actions._runtime(self.context,self.budget,live=True,
                              **({'initial_a': self.initial_a} if self.cycle else {}))
        self.actions._live_filesystem(self.context,self.budget)
        deadline=time.monotonic()+5
        while True:
            try:
                self.actions._host_operator(live=True)
                self.actions._host_api(live=True)
                return
            except DeploymentHold:
                if time.monotonic()>=deadline:
                    raise
                time.sleep(.2)

    def _restore_generated(self):
        self.actions._compose(self.context,self.budget,
            ['stop','--timeout','20',*SERVICES],timeout=30)
        self.actions._compose(self.context,self.budget,
            ['up','-d','--no-deps','--force-recreate','--wait','--wait-timeout','40',*SERVICES],timeout=60)
        try:
            self.actions._runtime(self.context,self.budget)
        except DeploymentHold:
            raise DeploymentHold('generated_runtime_check_failed') from None
        # Compose health does not prove that both host loopback routes have
        # finished binding after recreation. Only connection unavailability is
        # transient; a reachable endpoint reporting wrong state must stop.
        deadline=time.monotonic()+self.budget.timeout(10)
        last_unavailable='generated_api_readiness_timeout'
        while True:
            if min(deadline-time.monotonic(),self.budget.timeout()) < 2:
                raise DeploymentHold(last_unavailable)
            try:
                self.actions._host_api()
            except DeploymentHold as error:
                reason=str(error)
                if reason!='host_api_loopback_unavailable':
                    raise DeploymentHold('generated_api_state_check_failed') from None
                last_unavailable='generated_api_readiness_timeout'
                time.sleep(.2)
                continue
            if min(deadline-time.monotonic(),self.budget.timeout()) < 2:
                raise DeploymentHold('generated_operator_readiness_timeout')
            try:
                self.actions._host_operator()
                return
            except DeploymentHold as error:
                if str(error)!='host_operator_loopback_unavailable':
                    raise DeploymentHold('generated_operator_state_check_failed') from None
                last_unavailable='generated_operator_readiness_timeout'
                time.sleep(.2)

    def enter(self):
        """Expose an OFF live operator and matching API/workers; never call ON."""
        self.actions._host()
        self._profile()
        self.actions._postgres(self.context,self.budget)
        self.actions._live_filesystem(self.context,self.budget)
        self.actions._runtime(self.context,self.budget)
        self.actions._host_api()
        self.actions._host_operator()
        changed=False
        try:
            changed=True
            self.actions._compose(self.context,self.budget,
                ['stop','--timeout','20',*SERVICES],timeout=30)
            self._compose_live(['up','-d','--no-deps','--force-recreate','--wait',
                '--wait-timeout','40',*SERVICES])
            self._check_live_off()
            return {'gate':'PP_LIVE_READY_OFF','origin_id':'pp-live-pp',
                    'collector_enabled':False,'postgres_recreated':False,
                    'cloud_enabled':False,'retirement_enabled':False} | (
                        {'initial_a': self.initial_a} if self.cycle else {})
        except Exception:
            if changed:
                try:
                    # If an operator task started during transition, OFF must
                    # be established before returning to the generated profile.
                    self._live_off()
                    self._restore_generated()
                except Exception:
                    raise DeploymentHold('pp_live_transition_recovery_unproven') from None
            raise DeploymentHold('pp_live_transition_failed_recovered') from None

    def leave(self):
        """Turn durable writes OFF before returning all app services to generated."""
        self.actions._host()
        self._profile()
        self.actions._postgres(self.context,self.budget)
        self._live_off()
        self._restore_generated()
        return {'gate':'PP_GENERATED_RESTORED','origin_id':'generated-pp',
                'collector_enabled':False,'postgres_recreated':False,
                'cloud_enabled':False,'retirement_enabled':False}
