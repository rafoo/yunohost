# encoding: utf-8

import re
import os
import pwd
import subprocess

from yunohost.utils.error import YunohostError
from moulinette.utils.filesystem import read_file, write_to_file, chown, chmod, mkdir

SSHD_CONFIG_PATH = "/etc/ssh/sshd_config"


def user_ssh_allow(username):
    """
    Allow YunoHost user connect as ssh.

    Keyword argument:
        username -- User username
    """
    # TODO it would be good to support different kind of shells

    if not _get_user_for_ssh(username):
        raise YunohostError('user_unknown', user=username)

    from yunohost.utils.ldap import _get_ldap_interface
    ldap = _get_ldap_interface()
    ldap.update('uid=%s,ou=users' % username, {'loginShell': ['/bin/bash']})

    # Somehow this is needed otherwise the PAM thing doesn't forget about the
    # old loginShell value ?
    subprocess.call(['nscd', '-i', 'passwd'])


def user_ssh_disallow(username):
    """
    Disallow YunoHost user connect as ssh.

    Keyword argument:
        username -- User username
    """
    # TODO it would be good to support different kind of shells

    if not _get_user_for_ssh(username):
        raise YunohostError('user_unknown', user=username)

    from yunohost.utils.ldap import _get_ldap_interface
    ldap = _get_ldap_interface()
    ldap.update('uid=%s,ou=users' % username, {'loginShell': ['/bin/false']})

    # Somehow this is needed otherwise the PAM thing doesn't forget about the
    # old loginShell value ?
    subprocess.call(['nscd', '-i', 'passwd'])


def user_ssh_list_keys(username):
    user = _get_user_for_ssh(username, ["homeDirectory"])
    if not user:
        raise Exception("User with username '%s' doesn't exists" % username)

    authorized_keys_file = os.path.join(user["homeDirectory"][0], ".ssh", "authorized_keys")

    if not os.path.exists(authorized_keys_file):
        return {"keys": []}

    keys = []
    last_comment = ""
    for line in read_file(authorized_keys_file).split("\n"):
        # empty line
        if not line.strip():
            continue

        if line.lstrip().startswith("#"):
            last_comment = line.lstrip().lstrip("#").strip()
            continue

        # assuming a key per non empty line
        key = line.strip()
        keys.append({
            "key": key,
            "name": last_comment,
        })

        last_comment = ""

    return {"keys": keys}


def user_ssh_add_key(username, key, comment):
    user = _get_user_for_ssh(username, ["homeDirectory", "uid"])
    if not user:
        raise Exception("User with username '%s' doesn't exists" % username)

    authorized_keys_file = os.path.join(user["homeDirectory"][0], ".ssh", "authorized_keys")

    if not os.path.exists(authorized_keys_file):
        # ensure ".ssh" exists
        mkdir(os.path.join(user["homeDirectory"][0], ".ssh"),
              force=True, parents=True, uid=user["uid"][0])

        # create empty file to set good permissions
        write_to_file(authorized_keys_file, "")
        chown(authorized_keys_file, uid=user["uid"][0])
        chmod(authorized_keys_file, 0o600)

    authorized_keys_content = read_file(authorized_keys_file)

    authorized_keys_content += "\n"
    authorized_keys_content += "\n"

    if comment and comment.strip():
        if not comment.lstrip().startswith("#"):
            comment = "# " + comment
        authorized_keys_content += comment.replace("\n", " ").strip()
        authorized_keys_content += "\n"

    authorized_keys_content += key.strip()
    authorized_keys_content += "\n"

    write_to_file(authorized_keys_file, authorized_keys_content)


def user_ssh_remove_key(username, key):
    user = _get_user_for_ssh(username, ["homeDirectory", "uid"])
    if not user:
        raise Exception("User with username '%s' doesn't exists" % username)

    authorized_keys_file = os.path.join(user["homeDirectory"][0], ".ssh", "authorized_keys")

    if not os.path.exists(authorized_keys_file):
        raise Exception("this key doesn't exists ({} dosesn't exists)".format(authorized_keys_file))

    authorized_keys_content = read_file(authorized_keys_file)

    if key not in authorized_keys_content:
        raise Exception("Key '{}' is not present in authorized_keys".format(key))

    # don't delete the previous comment because we can't verify if it's legit

    # this regex approach failed for some reasons and I don't know why :(
    # authorized_keys_content = re.sub("{} *\n?".format(key),
    #                                  "",
    #                                  authorized_keys_content,
    #                                  flags=re.MULTILINE)

    authorized_keys_content = authorized_keys_content.replace(key, "")

    write_to_file(authorized_keys_file, authorized_keys_content)

#
# Helpers
#


def _get_user_for_ssh(username, attrs=None):
    def ssh_root_login_status():
        # XXX temporary placed here for when the ssh_root commands are integrated
        # extracted from https://github.com/YunoHost/yunohost/pull/345
        # XXX should we support all the options?
        # this is the content of "man sshd_config"
        # PermitRootLogin
        #     Specifies whether root can log in using ssh(1).  The argument must be
        #     “yes”, “without-password”, “forced-commands-only”, or “no”.  The
        #     default is “yes”.
        sshd_config_content = read_file(SSHD_CONFIG_PATH)

        if re.search("^ *PermitRootLogin +(no|forced-commands-only) *$",
                     sshd_config_content, re.MULTILINE):
            return {"PermitRootLogin": False}

        return {"PermitRootLogin": True}

    if username == "root":
        root_unix = pwd.getpwnam("root")
        return {
            'username': 'root',
            'fullname': '',
            'mail': '',
            'ssh_allowed': ssh_root_login_status()["PermitRootLogin"],
            'shell': root_unix.pw_shell,
            'home_path': root_unix.pw_dir,
        }

    if username == "admin":
        admin_unix = pwd.getpwnam("admin")
        return {
            'username': 'admin',
            'fullname': '',
            'mail': '',
            'ssh_allowed': admin_unix.pw_shell.strip() != "/bin/false",
            'shell': admin_unix.pw_shell,
            'home_path': admin_unix.pw_dir,
        }

    # TODO escape input using https://www.python-ldap.org/doc/html/ldap-filter.html
    from yunohost.utils.ldap import _get_ldap_interface
    ldap = _get_ldap_interface()
    user = ldap.search('ou=users,dc=yunohost,dc=org',
                       '(&(objectclass=person)(uid=%s))' % username,
                       attrs)

    assert len(user) in (0, 1)

    if not user:
        return None

    return user[0]
