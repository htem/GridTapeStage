#!/usr/bin/env python
"""
Important commands are:
    update : update temcagt repo on all nodes
    start_cameras : start all camera nodes
    kill_cameras : stop all camera nodes
    start_controls : start motion and control nodes
    kill_controls : stop motion and control nodes
"""

import time
from fabric.api import run, env, roles, execute, runs_once

env.use_ssh_config = True

camera_hosts = ['cam0', 'cam1', 'cam2', 'cam3']
control_hosts = ['control']
tapecamera_hosts = ['tapecamera']
all_hosts = camera_hosts + control_hosts + tapecamera_hosts

#env.hosts.extend(all_hosts)
env.roledefs.update({
    'camera': camera_hosts,
    'control': control_hosts,
    'tapecamera': tapecamera_hosts,
    'all': all_hosts,
})

if not len(env.roles):
    env.roles = ['all']


def command(cmd):
    """Run a remote command"""
    run(cmd)


def venv_command(cmd):
    """Run a remote command inside the temcagt virtual environment"""
    run("source ~/.virtualenvs/temcagt/bin/activate && umask 0002 &&" + cmd)

def temcagt(cmd):
    """Run a temcagt command (e.g temcagt kill, temcagt status)"""
    venv_command("temcagt " + cmd)


def status():
    """Get the status of all temcagt nodes"""
    temcagt("status")


@roles('camera')
def kill_cameras():
    temcagt("kill")


@roles('camera')
def kill9_cameras():
    temcagt("kill9")


@roles('camera')
def start_cameras():
    temcagt("start")


@roles('tapecamera')
def start_tapecamera():
    temcagt('start')


@roles('tapecamera')
def kill_tapecamera():
    temcagt('kill')


@roles('tapecamera')
def kill9_tapecamera():
    temcagt('kill9')


@roles('control')
def kill_controls():
    temcagt("kill")


@roles('control')
def kill9_controls():
    temcagt("kill9")


@roles('control')
def start_controls():
    temcagt("start")


@runs_once
def start():
    execute(start_cameras)
    execute(start_tapecamera)
    execute(start_controls)


@runs_once
def kill():
    execute(kill_controls)
    execute(kill_tapecamera)
    execute(kill_cameras)


@runs_once
def kill9():
    execute(kill9_controls)
    execute(kill9_tapecamera)
    execute(kill9_cameras)


def pull(repo):
    """Pull a repo (in the form of htem/temcagt)"""
    command("cd ~/Repositories/" + repo + " && git pull")


def install(repo):
    """Pull and install a repo (useful for htem/temcagt repo)"""
    venv_command(
        "cd ~/Repositories/" + repo + " && git pull && pip install -e .")


def update():
    pull("htem/pyandor")
    install("htem/temcagt")
