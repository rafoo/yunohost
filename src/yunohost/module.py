# -*- coding: utf-8 -*-

""" License

    Copyright (C) 2020 YunoHost

    This program is free software; you can redistribute it and/or modify
    it under the terms of the GNU Affero General Public License as published
    by the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU Affero General Public License for more details.

    You should have received a copy of the GNU Affero General Public License
    along with this program; if not, see http://www.gnu.org/licenses

"""

""" yunohost_module.py

    Manage system modules
"""

import os
import re
import time
import yaml
import subprocess

from glob import glob
from datetime import datetime

from moulinette import m18n
from yunohost.utils.error import YunohostError
from moulinette.utils.log import getActionLogger
from moulinette.utils.filesystem import read_file, append_to_file, write_to_file

MOULINETTE_LOCK = "/var/run/moulinette_yunohost.lock"

logger = getActionLogger('yunohost.module')


def module_add(name, description=None, log=None, log_type="file", test_status=None, test_conf=None, needs_exposed_ports=None, need_lock=False, status=None):
    """
    Add a custom system module

    Keyword argument:
        name -- Module name to add
        description -- description of the module
        log -- Absolute path to log file to display
        log_type -- Specify if the corresponding log is a file or a systemd log
        test_status -- Specify a custom bash command to check the status of the service. N.B. : it only makes sense to specify this if the corresponding systemd service does not return the proper information.
        test_conf -- Specify a custom bash command to check if the configuration of the module is valid or broken, similar to nginx -t.
        needs_exposed_ports -- A list of ports that needs to be publicly exposed for the module to work as intended.
        need_lock -- Use this option to prevent deadlocks if the module does invoke yunohost commands.
        status -- Deprecated, doesn't do anything anymore. Use test_status instead.
    """
    modules = _get_modules()

    modules[name] = {}

    if log is not None:
        if not isinstance(log, list):
            log = [log]

        modules[name]['log'] = log

        if not isinstance(log_type, list):
            log_type = [log_type]

        if len(log_type) < len(log):
            log_type.extend([log_type[-1]] * (len(log) - len(log_type))) # extend list to have the same size as log

        if len(log_type) == len(log):
            modules[name]['log_type'] = log_type
        else:
            raise YunohostError('module_add_failed', module=name)

    if description:
        modules[name]['description'] = description
    else:
        # Try to get the description from systemd service
        out = subprocess.check_output("systemctl show %s | grep '^Description='" % name, shell=True).strip()
        out = out.replace("Description=", "")
        # If the service does not yet exists or if the description is empty,
        # systemd will anyway return foo.service as default value, so we wanna
        # make sure there's actually something here.
        if out == name + ".service":
            logger.warning("/!\\ Packager ! You added a custom system module without specifying a description. Please add a proper Description in the systemd configuration, or use --description to explain what the module does in a similar fashion to existing modules.")
        else:
            modules[name]['description'] = out

    if need_lock:
        modules[name]['need_lock'] = True

    if test_status:
        modules[name]["test_status"] = test_status

    if test_conf:
        modules[name]["test_conf"] = test_conf

    if needs_exposed_ports:
        modules[name]["needs_exposed_ports"] = needs_exposed_ports

    try:
        _save_modules(modules)
    except:
        # we'll get a logger.warning with more details in _save_modules
        raise YunohostError('module_add_failed', module=name)

    logger.success(m18n.n('module_added', module=name))


def module_remove(name):
    """
    Remove a custom system module

    Keyword argument:
        name -- Module name to remove

    """
    modules = _get_modules()

    try:
        del modules[name]
    except KeyError:
        raise YunohostError('module_unknown', module=name)

    try:
        _save_modules(modules)
    except:
        # we'll get a logger.warning with more details in _save_modules
        raise YunohostError('module_remove_failed', module=name)

    logger.success(m18n.n('module_removed', module=name))

def _get_modules():
    """
    Get a dict of managed modules with their parameters

    """
    try:
        with open('/etc/yunohost/modules.yml', 'r') as f:
            modules = yaml.load(f)
    except:
        return {}

    # some modules are marked as None to remove them from YunoHost
    # filter this
    for key, value in modules.items():
        if value is None:
            del modules[key]

    return modules

def _save_modules(modules):
    """
    Save managed modules to files

    Keyword argument:
        modules -- A dict of managed modules with their parameters

    """
    try:
        with open('/etc/yunohost/modules.yml', 'w') as f:
            yaml.safe_dump(modules, f, default_flow_style=False)
    except Exception as e:
        logger.warning('Error while saving system modules, exception: %s', e, exc_info=1)
        raise

    
