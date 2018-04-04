from __future__ import unicode_literals

from collections import OrderedDict, defaultdict

from copy import deepcopy

import six
from django.utils import timezone
from six import python_2_unicode_compatible

from processlib.models import Process, ActivityInstance

_FLOWS = {}


def get_flows():
    return _FLOWS.items()


def get_flow(label):
    return _FLOWS[label]


def flow_label(flow):
    return '{}.{}'.format(flow.__module__, flow.name)  # FIXME app label?


def register_flow(flow):
    _FLOWS[flow.label] = flow


@python_2_unicode_compatible
class Flow(object):
    def __init__(self, name, process_model=Process, activity_model=ActivityInstance,
                 verbose_name=None):
        self.name = name
        self.activity_model = activity_model
        self.verbose_name = verbose_name
        self.process_model = process_model
        self._activities = OrderedDict()
        self._activity_kwargs = {}
        self._in_edges = defaultdict(list)
        self._out_edges = defaultdict(list)
        self.label = flow_label(self)
        register_flow(self)

    def copy(self, name, process_model=None, activity_model=None, verbose_name=None):
        copy = deepcopy(self)
        copy.name = name
        copy.label = flow_label(copy)
        copy.verbose_name = verbose_name
        if process_model:
            copy.process_model = process_model
        if activity_model:
            copy.activity_model = activity_model

    def __str__(self):
        return self.verbose_name or self.name or repr(self)

    def start_with(self, activity_name, activity, **activity_kwargs):
        if self._activities:
            raise ValueError("start_with has to be the first activity added")

        self._activities[activity_name] = activity
        self._activity_kwargs[activity_name] = activity_kwargs
        return self

    def and_then(self, activity_name, activity, **activity_kwargs):
        predecessor = list(self._activities)[-1]  # implicitly connect to previously added
        return self.add_activity(activity_name, activity, predecessor, **activity_kwargs)

    def add_activity(self, activity_name, activity, after=None, wait_for=None, **activity_kwargs):
        if not self._activities:
            raise ValueError("A start activity has to be added first with start_with")

        if after is None:
            after = list(self._activities)[-1]  # implicitly connect to previously added

        predecessors = [after] if after else []

        if wait_for:
            if isinstance(wait_for, six.string_types):
                raise TypeError("wait_for should be a list or tuple")

            activity_kwargs['wait_for'] = wait_for

            for name in wait_for:
                if name not in predecessors:
                    predecessors.append(name)

                if self._activity_kwargs[name].get('skip_if'):
                    raise ValueError("Never wait for conditional activities.")

        for predecessor in predecessors:
            self._out_edges[predecessor].append(activity_name)
            self._in_edges[activity_name].append(predecessor)

        self._activities[activity_name] = activity
        self._activity_kwargs[activity_name] = activity_kwargs

        return self

    def _get_activity_by_name(self, process, activity_name):
        return self._activities[activity_name](flow=self, process=process, instance=None,
                                               name=activity_name,
                                               **self._activity_kwargs[activity_name])

    def get_activity_by_instance(self, instance):
        activity_name = instance.activity_name
        process = self.process_model._default_manager.get(pk=instance.process_id)
        kwargs = self._activity_kwargs[activity_name]
        return self._activities[activity_name](
            flow=self, process=process, instance=instance, name=activity_name,
            **kwargs
        )

    def get_start_activity(self, **kwargs):
        process = self.process_model(
            flow_label=self.label,
            started_at=timezone.now(),
            **kwargs
        )
        activity = self._get_activity_by_name(process, list(self._activities)[0])
        activity.instantiate()
        return activity
