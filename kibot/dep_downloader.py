# -*- coding: utf-8 -*-
# Copyright (c) 2022 Salvador E. Tropea
# Copyright (c) 2022 Instituto Nacional de Tecnología Industrial
# License: GPL-3.0
# Project: KiBot (formerly KiPlot)
import os
import re
import subprocess
import requests
import platform
import io
import tarfile
import stat
import json
import fnmatch
import site
from sys import exit, stdout
from shutil import which, rmtree, move
from math import ceil
from .kiplot import search_as_plugin
from .misc import MISSING_TOOL, TRY_INSTALL_CHECK, W_DOWNTOOL, W_MISSTOOL, USER_AGENT
from . import log

logger = log.get_logger()
ver_re = re.compile(r'(\d+)\.(\d+)(?:\.(\d+))?(?:[\.-](\d+))?')
home_bin = os.environ.get('HOME') or os.environ.get('username')
if home_bin is not None:
    home_bin = os.path.join(home_bin, '.local', 'share', 'kibot', 'bin')
EXEC_PERM = stat.S_IRWXU | stat.S_IRGRP | stat.S_IXGRP | stat.S_IROTH | stat.S_IXOTH
last_stderr = None
version_check_fail = False
binary_tools_cache = {}


def show_progress(done):
    stdout.write("\r[%s%s] %3d%%" % ('=' * done, ' ' * (50-done), 2*done))
    stdout.flush()


def end_show_progress():
    stdout.write("\n")
    stdout.flush()


def download(url, progress=True):
    logger.debug('- Trying to download '+url)
    r = requests.get(url, allow_redirects=True, headers={'User-Agent': USER_AGENT}, timeout=20, stream=True)
    if r.status_code != 200:
        logger.debug('- Failed to download `{}`'.format(url))
        return None
    total_length = r.headers.get('content-length')
    logger.debugl(2, '- Total length: '+str(total_length))
    if total_length is None:  # no content length header
        return r.content
    dl = 0
    total_length = int(total_length)
    chunk_size = ceil(total_length/50)
    if chunk_size < 4096:
        chunk_size = 4096
    logger.debugl(2, '- Chunk size: '+str(chunk_size))
    rdata = b''
    if progress:
        show_progress(0)
    for data in r.iter_content(chunk_size=chunk_size):
        dl += len(data)
        rdata += data
        done = int(50 * dl / total_length)
        if progress:
            show_progress(done)
    if progress:
        end_show_progress()
    return rdata


def write_executable(command, content):
    dest_bin = os.path.join(home_bin, command)
    os.makedirs(home_bin, exist_ok=True)
    with open(dest_bin, 'wb') as f:
        f.write(content)
    os.chmod(dest_bin, EXEC_PERM)
    return dest_bin


def try_download_tar_ball(dep, url, name, name_in_tar=None):
    if name_in_tar is None:
        name_in_tar = name
    content = download(url)
    if content is None:
        return None
    # Try to extract the binary
    dest_file = None
    try:
        with tarfile.open(fileobj=io.BytesIO(content), mode='r') as tar:
            for entry in tar:
                if entry.type != tarfile.REGTYPE or not fnmatch.fnmatch(entry.name, name_in_tar):
                    continue
                dest_file = write_executable(name, tar.extractfile(entry).read())
    except Exception as e:
        logger.debug('- Failed to extract {}'.format(e))
        return None
    # Is this usable?
    cmd = check_tool_binary_version(dest_file, dep, no_cache=True)
    if cmd is None:
        return None
    # logger.warning(W_DOWNTOOL+'Using downloaded `{}` tool, please visit {} for details'.format(name, dep.url))
    return cmd


def untar(data):
    base_dir = os.path.join(home_bin, '..')
    dir_name = None
    try:
        with tarfile.open(fileobj=io.BytesIO(data), mode='r') as tar:
            for entry in tar:
                name = os.path.join(base_dir, entry.name)
                logger.debugl(3, name)
                if entry.type == tarfile.DIRTYPE:
                    os.makedirs(name, exist_ok=True)
                    if dir_name is None:
                        dir_name = name
                elif entry.type == tarfile.REGTYPE:
                    with open(name, 'wb') as f:
                        f.write(tar.extractfile(entry).read())
                elif entry.type == tarfile.SYMTYPE:
                    os.symlink(os.path.join(base_dir, entry.linkname), name)
                else:
                    logger.warning('- Unsupported tar element: '+entry.name)
    except Exception as e:
        logger.debug('- Failed to extract {}'.format(e))
        return None
    if dir_name is None:
        return None
    return os.path.abspath(dir_name)


def pytool_downloader(dep, system, plat):
    # Check if we have a github repo as download page
    logger.debug('- Download URL: '+str(dep.url_down))
    if not dep.url_down:
        return None
    res = re.match(r'^https://github.com/([^/]+)/([^/]+)/', dep.url_down)
    if res is None:
        return None
    user = res.group(1)
    prj = res.group(2)
    logger.debugl(2, '- GitHub repo: {}/{}'.format(user, prj))
    url = 'https://api.github.com/repos/{}/{}/releases/latest'.format(user, prj)
    # Check if we have pip and wheel
    pip_command = which('pip3')
    if pip_command is not None:
        pip_ok = True
    else:
        pip_command = which('pip')
        pip_ok = pip_command is not None
    if not pip_ok:
        logger.warning(W_MISSTOOL+'Missing Python installation tool (pip)')
        return None
    logger.debugl(2, '- Pip command: '+pip_command)
    # Pip will fail to install downloaded packages if wheel isn't available
    try:
        import wheel
        wheel_ok = True
        logger.debugl(2, '- Wheel v{}'.format(wheel.__version__))
    except ImportError:
        wheel_ok = False
    if not wheel_ok:
        cmd = [pip_command, 'install', '--no-warn-script-location', '-U', 'wheel']
        logger.debug('- Trying to install wheel: `{}`'.format(cmd))
        try:
            res_run = subprocess.run(cmd, check=True, capture_output=True)
        except Exception as e:
            logger.debug('- Failed to install wheel ({})'.format(e))
            return None
    # Look for the last release
    data = download(url, progress=False)
    if data is None:
        return None
    try:
        data = json.loads(data)
        logger.debugl(4, 'Release information: {}'.format(data))
        url = data['tarball_url']
    except Exception as e:
        logger.debug('- Failed to find a download ({})'.format(e))
        return None
    logger.debugl(2, '- Tarball: '+url)
    # Download and uncompress the tarball
    dest = untar(download(url))
    if dest is None:
        return None
    logger.debugl(2, '- Uncompressed tarball to: '+dest)
    # Try to pip install it
    cmd = [pip_command, 'install', '-U', '--no-warn-script-location', '.']
    logger.debug('- Running: {}'.format(cmd))
    try:
        res_run = subprocess.run(cmd, check=True, capture_output=True, cwd=dest)
        logger.debugl(3, '- Output from pip:\n'+res_run.stdout.decode())
    except Exception as e:
        logger.debug('- Failed to install using pip ({})'.format(e))
        out = res_run.stderr.decode()
        if out:
            logger.debug('- StdErr: '+out)
        out = res_run.stdout.decode()
        if out:
            logger.debug('- StdOut: '+out)
        return None
    rmtree(dest)
    # Check it was successful
    return check_tool_binary_version(os.path.join(site.USER_BASE, 'bin', dep.command), dep, no_cache=True)


def git_downloader(dep, system, plat):
    # Currently only for Linux x86_64/x86_32
    # arm, arm64, mips64el and mipsel are also there, just not implemented
    if system != 'Linux' or not plat.startswith('x86_'):
        logger.debug('- No binary for this system')
        return None
    # Try to download it
    arch = 'amd64' if plat == 'x86_64' else 'i386'
    url = 'https://github.com/EXALAB/git-static/raw/master/output/'+arch+'/bin/git'
    content = download(url)
    if content is None:
        return None
    dest_bin = write_executable(dep.command+'.real', content.replace(b'/root/output', b'/tmp/kibogit'))
    # Now create the wrapper
    git_real = dest_bin
    dest_bin = dest_bin[:-5]
    logger.error(f'{dest_bin} -> {git_real}')
    if os.path.isfile(dest_bin):
        os.remove(dest_bin)
    with open(dest_bin, 'wt') as f:
        f.write('#!/bin/sh\n')
        f.write('rm /tmp/kibogit\n')
        f.write('ln -s {} /tmp/kibogit\n'.format(home_bin[:-3]))
        f.write('{} "$@"\n'.format(git_real))
    os.chmod(dest_bin, EXEC_PERM)
    return check_tool_binary_version(dest_bin, dep, no_cache=True)


def convert_downloader(dep, system, plat):
    # Currently only for Linux x86_64
    if system != 'Linux' or plat != 'x86_64':
        logger.debug('- No binary for this system')
        return None
    # Get the download page
    content = download(dep.url_down)
    if content is None:
        return None
    # Look for the URL
    res = re.search(r'href\s*=\s*"([^"]+)">magick<', content.decode())
    if not res:
        logger.debug('- No `magick` download')
        return None
    url = res.group(1)
    # Get the binary
    content = download(url)
    if content is None:
        return None
    # Can we run the AppImage?
    dest_bin = write_executable(dep.command, content)
    cmd = check_tool_binary_version(dest_bin, dep, no_cache=True)
    if cmd is not None:
        logger.warning(W_DOWNTOOL+'Using downloaded `{}` tool, please visit {} for details'.format(dep.name, dep.url))
        return cmd
    # Was because we don't have FUSE support
    if not ('libfuse.so' in last_stderr or 'FUSE' in last_stderr or last_stderr.startswith('fuse')):
        logger.debug('- Unknown fail reason: `{}`'.format(last_stderr))
        return None
    # Uncompress it
    unc_dir = os.path.join(home_bin, 'squashfs-root')
    if os.path.isdir(unc_dir):
        rmtree(unc_dir)
    cmd = [dest_bin, '--appimage-extract']
    logger.debug('- Running {}'.format(cmd))
    try:
        res_run = subprocess.run(cmd, check=True, capture_output=True, cwd=home_bin)
    except Exception as e:
        logger.debug('- Failed to execute `{}` ({})'.format(cmd[0], e))
        return None
    if not os.path.isdir(unc_dir):
        logger.debug('- Failed to uncompress `{}` ({})'.format(cmd[0], res_run.stderr.decode()))
        return None
    # Now copy the important stuff
    # Binaries
    src_dir, _, bins = next(os.walk(os.path.join(unc_dir, 'usr', 'bin')))
    if not len(bins):
        logger.debug('- No binaries found after extracting {}'.format(dest_bin))
        return None
    for f in bins:
        dst_file = os.path.join(home_bin, f)
        if os.path.isfile(dst_file):
            os.remove(dst_file)
        move(os.path.join(src_dir, f), dst_file)
    # Libs (to ~/.local/share/kibot/lib/ImageMagick/lib/ or similar)
    src_dir = os.path.join(unc_dir, 'usr', 'lib')
    if not os.path.isdir(src_dir):
        logger.debug('- No libraries found after extracting {}'.format(dest_bin))
        return None
    dst_dir = os.path.join(home_bin, '..', 'lib', 'ImageMagick')
    if os.path.isdir(dst_dir):
        rmtree(dst_dir)
    os.makedirs(dst_dir, exist_ok=True)
    move(src_dir, dst_dir)
    lib_dir = os.path.join(dst_dir, 'lib')
    # Config (to ~/.local/share/kibot/etc/ImageMagick-7/ or similar)
    src_dir, dirs, _ = next(os.walk(os.path.join(unc_dir, 'usr', 'etc')))
    if len(dirs) != 1:
        logger.debug('- More than one config dir found {}'.format(dirs))
        return None
    src_dir = os.path.join(src_dir, dirs[0])
    dst_dir = os.path.join(home_bin, '..', 'etc')
    os.makedirs(dst_dir, exist_ok=True)
    dst_dir_name = os.path.join(dst_dir, dirs[0])
    if os.path.isdir(dst_dir_name):
        rmtree(dst_dir_name)
    move(src_dir, dst_dir)
    # Now create the wrapper
    os.remove(dest_bin)
    magick_bin = dest_bin[:-len(dep.command)]+'magick'
    with open(dest_bin, 'wt') as f:
        f.write('#!/bin/sh\n')
        # Include the downloaded libs
        f.write('export LD_LIBRARY_PATH="{}:$LD_LIBRARY_PATH"\n'.format(lib_dir))
        # Also look for gs in our download dir
        f.write('export PATH="$PATH:{}"\n'.format(home_bin))
        # Get the config from the downloaded config
        f.write('export MAGICK_CONFIGURE_PATH="{}"\n'.format(dst_dir_name))
        # Use the `convert` tool
        f.write('{} convert "$@"\n'.format(magick_bin))
    os.chmod(dest_bin, EXEC_PERM)
    # Is this usable?
    return check_tool_binary_version(dest_bin, dep, no_cache=True)


def gs_downloader(dep, system, plat):
    # Currently only for Linux x86
    if system != 'Linux' or not plat.startswith('x86_'):
        logger.debug('- No binary for this system')
        return None
    # Get the download page
    url = 'https://api.github.com/repos/ArtifexSoftware/ghostpdl-downloads/releases/latest'
    r = requests.get(url, allow_redirects=True)
    if r.status_code != 200:
        logger.debug('- Failed to download `{}`'.format(dep.url_down))
        return None
    # Look for the valid tarball
    arch = 'x86_64' if plat == 'x86_64' else 'x86'
    url = None
    pattern = 'ghostscript*linux-'+arch+'*'
    try:
        data = json.loads(r.content)
        for a in data['assets']:
            if fnmatch.fnmatch(a['name'], pattern):
                url = a['browser_download_url']
    except Exception as e:
        logger.debug('- Failed to find a download ({})'.format(e))
    if url is None:
        logger.debug('- No suitable binary')
        return None
    # Try to download it
    res = try_download_tar_ball(dep, url, 'ghostscript', 'ghostscript-*/gs*')
    if res is not None:
        short_gs = res[:-11]+'gs'
        long_gs = res
        if not os.path.isfile(short_gs):
            os.symlink(long_gs, short_gs)
    return res


def rsvg_downloader(dep, system, plat):
    # Currently only for Linux x86_64
    if system != 'Linux' or plat != 'x86_64':
        logger.debug('- No binary for this system')
        return None
    # Get the download page
    url = 'https://api.github.com/repos/set-soft/rsvg-convert-aws-lambda-binary/releases/latest'
    r = requests.get(url, allow_redirects=True)
    if r.status_code != 200:
        logger.debug('- Failed to download `{}`'.format(dep.url_down))
        return None
    # Look for the valid tarball
    url = None
    try:
        data = json.loads(r.content)
        for a in data['assets']:
            if 'linux-x86_64' in a['name']:
                url = a['browser_download_url']
    except Exception as e:
        logger.debug('- Failed to find a download ({})'.format(e))
    if url is None:
        logger.debug('- No suitable binary')
        return None
    # Try to download it
    return try_download_tar_ball(dep, url, 'rsvg-convert')


def rar_downloader(dep, system, plat):
    # Get the download page
    r = requests.get(dep.url_down, allow_redirects=True)
    if r.status_code != 200:
        logger.debug('- Failed to download `{}`'.format(dep.url_down))
        return None
    # Try to figure out the right package
    OSs = {'Linux': 'rarlinux', 'Darwin': 'rarmacos'}
    if system not in OSs:
        return None
    name = OSs[system]
    if plat == 'arm64':
        name += '-arm'
    elif plat == 'x86_64':
        name += '-x64'
    elif plat == 'x86_32':
        name += '-x32'
    else:
        return None
    res = re.search('href="([^"]+{}[^"]+)"'.format(name), r.content.decode())
    if not res:
        return None
    # Try to download it
    return try_download_tar_ball(dep, dep.url+res.group(1), 'rar', name_in_tar='rar/rar')


def do_int(v):
    return int(v) if v is not None else 0


def run_command(cmd, only_first_line=True, pre_ver_text=None, no_err_2=False):
    global last_stderr
    try:
        res_run = subprocess.run(cmd, check=True, capture_output=True)
    except subprocess.CalledProcessError as e:
        if e.returncode != 2 or not no_err_2:
            logger.debug('- Failed to run %s, error %d' % (cmd[0], e.returncode))
            last_stderr = e.stderr.decode()
            if e.output:
                logger.debug('- Output from command: '+e.output.decode())
        return None
    except Exception as e:
        logger.debug('- Failed to run {}, error {}'.format(cmd[0], e))
        return None
    last_stderr = res_run.stderr.decode()
    res = res_run.stdout.decode().strip()
    if only_first_line:
        res = res.split('\n')[0]
    pre_vers = (cmd[0]+' version ', cmd[0]+' ', pre_ver_text)
    for pre_ver in pre_vers:
        if pre_ver and res.startswith(pre_ver):
            res = res[len(pre_ver):]
    res = ver_re.search(res)
    if res:
        return tuple(map(do_int, res.groups()))
    return None


def check_tool_binary_version(full_name, dep, no_cache=False):
    logger.debugl(2, '- Checking version for `{}`'.format(full_name))
    global version_check_fail
    version_check_fail = False
    if dep.no_cmd_line_version:
        # No way to know the version, assume we can use it
        logger.debugl(2, "- This tool doesn't have a version option")
        return full_name
    # Do we need a particular version?
    needs = (0, 0, 0)
    for r in dep.roles:
        if r.version and r.version > needs:
            needs = r.version
    if needs == (0, 0, 0):
        # Any version is Ok
        logger.debugl(2, '- No particular version needed')
    else:
        logger.debugl(2, '- Needed version {}'.format(needs))
    # Check the version
    if full_name in binary_tools_cache and not no_cache:
        version = binary_tools_cache[full_name]
        logger.debugl(2, '- Cached version {}'.format(version))
    else:
        cmd = [full_name, dep.help_option]
        if dep.is_kicad_plugin:
            cmd.insert(0, 'python3')
        version = run_command(cmd, no_err_2=dep.no_cmd_line_version_old)
        binary_tools_cache[full_name] = version
        logger.debugl(2, '- Found version {}'.format(version))
    version_check_fail = version is None or version < needs
    return None if version_check_fail else full_name


def check_tool_binary_system(dep):
    logger.debugl(2, '- Looking for tool `{}` at system level'.format(dep.command))
    if dep.is_kicad_plugin:
        full_name = search_as_plugin(dep.command, dep.plugin_dirs)
    else:
        full_name = which(dep.command)
    if full_name is None:
        return None
    return check_tool_binary_version(full_name, dep)


def using_downloaded(dep):
    logger.warning(W_DOWNTOOL+'Using downloaded `{}` tool, please visit {} for details'.format(dep.command, dep.url))


def check_tool_binary_local(dep):
    logger.debugl(2, '- Looking for tool `{}` at user level'.format(dep.command))
    home = os.environ.get('HOME') or os.environ.get('username')
    if home is None:
        return None
    full_name = os.path.join(home_bin, dep.command)
    if not os.path.isfile(full_name) or not os.access(full_name, os.X_OK):
        return None
    cmd = check_tool_binary_version(full_name, dep)
    if cmd is not None:
        using_downloaded(dep)
    return cmd


def check_tool_binary_python(dep):
    base = os.path.join(site.USER_BASE, 'bin')
    logger.debugl(2, '- Looking for tool `{}` at Python user site ({})'.format(dep.command, base))
    full_name = os.path.join(base, dep.command)
    if not os.path.isfile(full_name) or not os.access(full_name, os.X_OK):
        return None
    return check_tool_binary_version(full_name, dep)


def try_download_tool_binary(dep):
    if dep.downloader is None or home_bin is None:
        return None
    logger.info('- Trying to download {} ({})'.format(dep.name, dep.url_down))
    res = None
    # Determine the platform
    system = platform.system()
    plat = platform.platform()
    if 'x86_64' in plat or 'amd64' in plat:
        plat = 'x86_64'
    elif 'x86_32' in plat or 'i386' in plat:
        plat = 'x86_32'
    elif 'arm64' in plat:
        plat = 'arm64'
    else:
        plat = 'unk'
    logger.debug('- System: {} platform: {}'.format(system, plat))
    # res = dep.downloader(dep, system, plat)
    # return res
    try:
        res = dep.downloader(dep, system, plat)
        if res:
            using_downloaded(dep)
    except Exception as e:
        logger.error('- Failed to download {}: {}'.format(dep.name, e))
    return res


def check_tool_binary(dep):
    logger.debugl(2, '- Checking binary tool {}'.format(dep.name))
    cmd = check_tool_binary_system(dep)
    if cmd is not None:
        return cmd
    cmd = check_tool_binary_python(dep)
    if cmd is not None:
        return cmd
    cmd = check_tool_binary_local(dep)
    if cmd is not None:
        return cmd
    return try_download_tool_binary(dep)


def check_tool_python(dep):
    return None


def do_log_err(msg, fatal):
    if fatal:
        logger.error(msg)
    else:
        logger.warning(W_MISSTOOL+msg)


def get_version(role):
    if role.version:
        return ' (v'+'.'.join(map(str, role.version))+')'
    return ''


def show_roles(roles, fatal):
    optional = []
    for r in roles:
        if not r.mandatory:
            optional.append(r)
        output = r.output
    if output != 'global':
        do_log_err('Output that needs it: '+output, fatal)
    if optional:
        if len(optional) == 1:
            o = optional[0]
            desc = o.desc[0].lower()+o.desc[1:]
            do_log_err('Used to {}{}'.format(desc, get_version(o)), fatal)
        else:
            do_log_err('Used to:', fatal)
            for o in optional:
                do_log_err('- {}{}'.format(o.desc, get_version(o)), fatal)


def check_tool(dep, fatal=False):
    logger.debug('Starting tool check for {}'.format(dep.name))
    if dep.is_python:
        cmd = check_tool_python(dep)
    else:
        cmd = check_tool_binary(dep)
    logger.debug('- Returning `{}`'.format(cmd))
    if cmd is None:
        if version_check_fail:
            do_log_err('Upgrade `{}` command ({})'.format(dep.command, dep.name), fatal)
        else:
            do_log_err('Missing `{}` command ({}), install it'.format(dep.command, dep.name), fatal)
        if dep.url:
            do_log_err('Home page: '+dep.url, fatal)
        if dep.url_down:
            do_log_err('Download page: '+dep.url_down, fatal)
        if dep.deb_package:
            do_log_err('Debian package: '+dep.deb_package, fatal)
        show_roles(dep.roles, fatal)
        do_log_err(TRY_INSTALL_CHECK, fatal)
        if fatal:
            exit(MISSING_TOOL)
    return cmd