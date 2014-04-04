from datetime import datetime
from sqlalchemy import (Column, Integer, String, Boolean, ForeignKey, DateTime,
                        Table, Text)
from sqlalchemy.orm import relationship, backref
from sqlalchemy.orm.exc import DetachedInstanceError
from pecan import conf
from paddles.models import Base
from paddles.models.nodes import Node
from paddles.models.types import JSONType
from paddles.util import local_datetime_to_utc

job_nodes_table = Table(
    'job_nodes',
    Base.metadata,
    Column('node_id', Integer, ForeignKey('nodes.id'), primary_key=True),
    Column('job_id', Integer, ForeignKey('jobs.id'), primary_key=True)
)


class Job(Base):

    __tablename__ = 'jobs'
    id = Column(Integer, primary_key=True)
    posted = Column(DateTime, index=True)
    updated = Column(DateTime, index=True)
    run_id = Column(Integer, ForeignKey('runs.id', ondelete='CASCADE'))
    status = Column(String(32), index=True)

    archive_path = Column(String(512))
    description = Column(String(512))
    duration = Column(Integer)
    email = Column(String(128))
    failure_reason = Column(Text)
    flavor = Column(String(128))
    job_id = Column(String(32), index=True)
    kernel = Column(JSONType())
    last_in_suite = Column(Boolean())
    machine_type = Column(String(32))
    name = Column(String(512))
    nuke_on_error = Column(Boolean())
    os_type = Column(String(32))
    overrides = Column(JSONType())
    owner = Column(String(128))
    pid = Column(String(32))
    roles = Column(JSONType())
    sentry_event = Column(String(128))
    success = Column(Boolean(), index=True)
    targets = Column(JSONType())
    target_nodes = relationship("Node", secondary=job_nodes_table,
                                backref=backref('jobs'))
    tasks = Column(JSONType())
    teuthology_branch = Column(String(32))
    verbose = Column(Boolean())

    allowed_keys = (
        "archive_path",
        "description",
        "duration",
        "email",
        "failure_reason",
        "flavor",
        "job_id",
        "kernel",
        "last_in_suite",
        "machine_type",
        "name",
        "nuke_on_error",
        "os_type",
        "overrides",
        "owner",
        "pid",
        "roles",
        "sentry_event",
        "status",
        "success",
        "targets",
        "tasks",
        "teuthology_branch",
        "verbose",
    )

    allowed_statuses = (
        "pass",
        "fail",
        "running",
        "dead",
        "unknown",
    )

    def __init__(self, json_data, run):
        self.run = run
        self.posted = datetime.utcnow()
        self.set_or_update(json_data)

    def set_or_update(self, json_data):
        self.__changed = False
        status_map = {True: 'pass',
                      False: 'fail',
                      None: 'unknown',
                      }
        success_map = {'pass': True,
                       'fail': False,
                       'dead': False,
                       'running': None,
                       }

        old_status = self.status
        if 'status' in json_data:
            status = json_data.pop('status')
            if status not in self.allowed_statuses:
                raise ValueError("Job status must be one of: %s" %
                                 self.allowed_statuses)
            if status == 'dead' and self.success is not None:
                self.update_attr('status', status_map.get(self.success))
            else:
                self.update_attr('status', status)
                json_data['success'] = success_map.get(status)
        elif 'success' in json_data:
            success = json_data.pop('success')
            self.update_attr('status', status_map.get(success))
            self.update_attr('success', success)
        else:
            self.update_attr('status', 'unknown')
            self.update_attr('success', None)

        if (self.status is not None and self.status != old_status and
                self.status not in self.run.status):
            self.run.set_status()

        if len(json_data.get('targets', {})) > len(self.target_nodes):
            # Populate self.target_nodes, creating Node objects if necessary
            targets = json_data['targets']
            for target_key in targets.keys():
                hostname = target_key.split('@')[1]
                node_q = Node.query.filter(Node.name == hostname)
                if node_q.count():
                    node = node_q.one()
                else:
                    node = Node(name=hostname)
                    mtype = json_data.get('machine_type', '')
                    if mtype and mtype in Node.machine_types:
                        node.machine_type = mtype
                if node not in self.target_nodes:
                    self.target_nodes.append(node)

        for k, v in json_data.items():
            key = k.replace('-', '_')
            # Handle teuthology transition from sentry_events -> sentry_event
            if key == 'sentry_events' and v != []:
                key = 'sentry_event'
                v = v[0]
            elif key == 'updated':
                self.set_updated(v)
                continue
            if key in self.allowed_keys:
                self.update_attr(key, v)
        if self.__changed and 'updated' not in json_data:
            self.updated = datetime.utcnow()

    def update_attr(self, attr_name, new_value):
        """
        Compare getattr(self, attr_name) with new_value. If equal, do nothing.
        Else, set self.__changed to True and update the value.

        This is used by set_or_update() to determine whethor or not
        self.updated should be... updated.
        """
        if getattr(self, attr_name) != new_value:
            setattr(self, attr_name, new_value)
            self.__changed = True

    def set_updated(self, local_str):
        """
        Given a string in the format of '%Y-%m-%d %H:%M:%S', in the local
        timezone, create a datetime object, convert it to UTC, and store it in
        self.updated.
        """
        local_dt = datetime.strptime(local_str, '%Y-%m-%d %H:%M:%S')
        utc_dt = local_datetime_to_utc(local_dt)
        self.updated = utc_dt

    def update(self, json_data):
        self.set_or_update(json_data)

    @property
    def href(self):
        return "%s/runs/%s/jobs/%s/" % (conf.address, self.run.name,
                                        self.job_id),

    @property
    def log_href(self):
        return conf.job_log_href_templ.format(run_name=self.run.name,
                                              job_id=self.job_id)

    def __repr__(self):
        try:
            return '<Job %r>' % self.job_id
        except DetachedInstanceError:
            return '<Job detached>'

    def __json__(self):
        json_ = dict(
            log_href=self.log_href
        )
        for key in self.allowed_keys + ('posted', 'updated'):
            json_[key] = getattr(self, key)

        return json_
