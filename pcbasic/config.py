"""
PC-BASIC - config.py
Configuration file and command-line options parser

(c) 2013, 2014, 2015, 2016 Rob Hagemans
This file is released under the GNU GPL version 3 or later.
"""

import os
import sys
import ConfigParser
import logging
import zipfile
import codecs

import plat
if plat.system == b'Windows':
    import ctypes
    import ctypes.wintypes


def get_logger(logfile=None):
    """Use the awkward logging interface as we can only use basicConfig once."""
    l = logging.getLogger(__name__)
    l.setLevel(logging.INFO)
    if logfile:
        h = logging.FileHandler(logfile, mode=b'w')
    else:
        h = logging.StreamHandler()
    h.setLevel(logging.INFO)
    h.setFormatter(logging.Formatter(u'%(levelname)s: %(message)s'))
    l.addHandler(h)
    return l


def get_unicode_argv():
    """ Convert command-line arguments to unicode. """
    if plat.system == b'Windows':
        # see http://code.activestate.com/recipes/572200-get-sysargv-with-unicode-characters-under-windows/
        GetCommandLineW = ctypes.cdll.kernel32.GetCommandLineW
        GetCommandLineW.argtypes = []
        GetCommandLineW.restype = ctypes.wintypes.LPCWSTR
        cmd = GetCommandLineW()
        argc = ctypes.c_int(0)
        CommandLineToArgvW = ctypes.windll.shell32.CommandLineToArgvW
        CommandLineToArgvW.argtypes = [ctypes.wintypes.LPCWSTR, ctypes.POINTER(ctypes.c_int)]
        CommandLineToArgvW.restype = ctypes.POINTER(ctypes.wintypes.LPWSTR)
        argv = CommandLineToArgvW(cmd, ctypes.byref(argc))
        argv = [argv[i] for i in xrange(argc.value)]
        # clip off the python interpreter call, if we use it
        if argv[0][:6].lower() == u'python':
            argv = argv[1:]
        return argv
    else:
        # the official parameter should be LC_CTYPE but that's None in my locale
        # on windows, this would only work if the mbcs CP_ACP includes the characters we need
        return [arg.decode(plat.preferred_encoding) for arg in sys.argv]

def append_arg(args, key, value):
    """Update a single list-type argument by appending a value"""
    if key in args and args[key]:
        if value:
            args[key] += u',' + value
    else:
        args[key] = value

def safe_split(s, sep):
    """Split an argument by separator, always return two elements"""
    slist = s.split(sep, 1)
    s0 = slist[0]
    if len(slist) > 1:
        s1 = slist[1]
    else:
        s1 = u''
    return s0, s1


class Settings(object):
    """Read and retrieve command-line settings and options"""

    # system-wide config path
    system_config_path = os.path.join(plat.system_config_dir, u'default.ini')

    #user and local config files
    config_name = u'PCBASIC.INI'
    user_config_path = os.path.join(plat.user_config_dir, config_name)

    # by default, load what's in section [pcbasic] and override with anything
    # in os-specific section [windows] [android] [linux] [osx] [unknown_os]
    default_presets = [u'pcbasic', plat.system.lower().decode('ascii')]

    # get supported codepages
    encodings = sorted([ x[0] for x in [ c.split(u'.ucp')
                         for c in os.listdir(plat.encoding_dir) ] if len(x)>1])
    # get supported font families
    families = sorted(list(set([ x[0] for x in [ c.split(u'_')
                      for c in os.listdir(plat.font_dir) ] if len(x)>1])))

    # number of positional arguments
    positional = 2

    # GWBASIC invocation, for reference:
    # GWBASIC [prog] [<inp] [[>]>outp] [/f:n] [/i] [/s:n] [/c:n] [/m:[n][,m]] [/d]
    #   /d      Allow double-precision ATN, COS, EXP, LOG, SIN, SQR, and TAN.
    #   /f:n    Set maximum number of open files to n. Default is 3.
    #           Each additional file reduces free memory by 322 bytes.
    #   /s:n    Set the maximum record length for RANDOM files.
    #           Default is 128, maximum is 32768.
    #   /c:n    Set the COM receive buffer to n bytes.
    #           If n==0, disable the COM ports.
    #   /i      Statically allocate file control blocks and data buffer.
    #           NOTE: this appears to be always the case in GW-BASIC, as here.
    #   /m:n,m  Set the highest memory location to n (default 65534) and maximum
    #           BASIC memory to m*16 bytes (default is all available).
    short_args = {
        u'd': u'double',
        u'f': u'max-files',
        u's': u'max-reclen',
        u'c': u'serial-buffer-size',
        u'm': u'max-memory',
        u'i': u'',
        u'b': u'interface=cli',
        u't': u'interface=text',
        u'n': u'interface=none',
        u'l': u'load',
        u'h': u'help',
        u'r': u'run',
        u'e': u'exec',
        u'q': u'quit',
        u'k': u'keys',
        u'v': u'version',
        u'w': u'wait',
        }

    # all long-form arguments
    arguments = {
        u'input': {u'type': u'string', u'default': u'', },
        u'output': {u'type': u'string', u'default': u'', },
        u'append': {u'type': u'bool', u'default': False, },
        u'interface': {
            u'type': u'string', u'default': u'',
            u'choices': (u'', u'none', u'cli', u'text', u'graphical',
                        u'ansi', u'curses', u'pygame', u'sdl2'), },
        u'load': {u'type': u'string', u'default': u'', },
        u'run': {u'type': u'string', u'default': u'',  },
        u'convert': {u'type': u'string', u'default': u'', },
        u'help': {u'type': u'bool', u'default': False, },
        u'keys': {u'type': u'string', u'default': u'', },
        u'exec': {u'type': u'string', u'default': u'',  },
        u'quit': {u'type': u'bool', u'default': False,},
        u'double': {u'type': u'bool', u'default': False,},
        u'max-files': {u'type': u'int', u'default': 3,},
        u'max-reclen': {u'type': u'int', u'default': 128,},
        u'serial-buffer-size': {u'type': u'int', u'default': 256,},
        u'peek': {u'type': u'string', u'list': u'*', u'default': [],},
        u'lpt1': {u'type': u'string', u'default': u'PRINTER:',},
        u'lpt2': {u'type': u'string', u'default': u'',},
        u'lpt3': {u'type': u'string', u'default': u'',},
        u'cas1': {u'type': u'string', u'default': u'',},
        u'com1': {u'type': u'string', u'default': u'',},
        u'com2': {u'type': u'string', u'default': u'',},
        u'codepage': {u'type': u'string', u'choices': encodings, u'default': u'437',},
        u'font': {
            u'type': u'string', u'list': u'*', u'choices': families,
            u'default': [u'unifont', u'univga', u'freedos'],},
        u'nosound': {u'type': u'bool', u'default': False, },
        u'dimensions': {u'type': u'int', u'list': 2, u'default': None,},
        u'fullscreen': {u'type': u'bool', u'default': False,},
        u'nokill': {u'type': u'bool', u'default': False,},
        u'debug': {u'type': u'bool', u'default': False,},
        u'strict-hidden-lines': {u'type': u'bool', u'default': False,},
        u'strict-protect': {u'type': u'bool', u'default': False,},
        u'capture-caps': {u'type': u'bool', u'default': False,},
        u'mount': {u'type': u'string', u'list': u'*', u'default': [],},
        u'resume': {u'type': u'bool', u'default': False,},
        u'strict-newline': {u'type': u'bool', u'default': False,},
        u'syntax': {
            u'type': u'string', u'choices': (u'advanced', u'pcjr', u'tandy'),
            u'default': u'advanced',},
        u'pcjr-term': {u'type': u'string', u'default': u'',},
        u'video': {
            u'type': u'string', u'default': 'vga',
            u'choices': (u'vga', u'ega', u'cga', u'cga_old', u'mda', u'pcjr', u'tandy',
                         u'hercules', u'olivetti'), },
        u'map-drives': {u'type': u'bool', u'default': False,},
        u'cga-low': {u'type': u'bool', u'default': False,},
        u'nobox': {u'type': u'bool', u'default': False,},
        u'utf8': {u'type': u'bool', u'default': False,},
        u'border': {u'type': u'int', u'default': 5,},
        u'pen': {
            u'type': u'string', u'default': u'left',
            u'choices': (u'left', u'middle', u'right', u'none',), },
        u'copy-paste': {u'type': u'string', u'list': 2, u'default': [u'left', u'middle'],
                       u'choices': (u'left', u'middle', u'right', u'none',),},
        u'state': {u'type': u'string', u'default': u'',},
        u'mono-tint': {u'type': u'int', u'list': 3, u'default': [255, 255, 255],},
        u'monitor': {
            u'type': u'string', u'choices': (u'rgb', u'composite', u'mono'),
            u'default': u'rgb',},
        u'aspect': {u'type': u'int', u'list': 2, u'default': [4, 3],},
        u'scaling': {u'type': u'string', u'choices':(u'smooth', u'native', u'crisp'), u'default': u'smooth',},
        u'version': {u'type': u'bool', u'default': False,},
        u'config': {u'type': u'string', u'default': u'',},
        u'logfile': {u'type': u'string', u'default': u'',},
        # negative list length means 'optionally up to'
        u'max-memory': {u'type': u'int', u'list': -2, u'default': [65534, 4096]},
        u'allow-code-poke': {u'type': u'bool', u'default': False,},
        u'reserved-memory': {u'type': u'int', u'default': 3429,},
        u'caption': {u'type': u'string', u'default': 'PC-BASIC',},
        u'text-width': {u'type': u'int', u'choices':(40, 80), u'default': 80,},
        u'video-memory': {u'type': u'int', u'default': 262144,},
        u'shell': {u'type': u'string', u'default': u'none',},
        u'print-trigger': {u'type': u'string', u'choices':(u'close', u'page', u'line'), u'default': u'close',},
        u'altgr': {u'type': u'bool', u'default': True,},
        u'ctrl-c-break': {u'type': u'bool', u'default': True,},
        u'wait': {u'type': u'bool', u'default': False,},
        u'current-device': {u'type': u'string', u'default': 'Z'},
    }


    def __init__(self):
        """Initialise settings"""
        # convert arguments to unicode using preferred encoding
        uargv = get_unicode_argv()
        # first parse a logfile argument, if any
        for args in uargv:
            if args[:9] == u'--logfile':
                logfile = args[10:]
                break
        else:
            logfile = None
        self._logger = get_logger(logfile)
        # create user config file if needed
        if not os.path.exists(self.user_config_path):
            try:
                os.makedirs(plat.user_config_dir)
            except OSError:
                pass
            self.build_default_config_file(self.user_config_path)
        # store options in options dictionary
        self._options = self._retrieve_options(uargv)

    def _retrieve_options(self, uargv):
        """Retrieve command line and option file options"""
        # convert command line arguments to string dictionary form
        remaining = self._get_arguments(uargv[1:])
        # unpack any packages
        package = self._parse_package(remaining)
        # get preset groups from specified config file
        preset_dict = self._parse_config(remaining)
        # set defaults based on presets
        args = self._parse_presets(remaining, preset_dict)
        # local config file settings override preset settings
        self._merge_arguments(args, preset_dict[u'pcbasic'])
        # parse rest of command line
        self._merge_arguments(args, self._parse_args(remaining))
        # clean up arguments
        self._clean_arguments(args)
        if package:
            # do not resume from a package
            args['resume'] = False
        return args

    def get(self, name, get_default=True):
        """Get value of option; choose whether to get default or None if unspecified"""
        try:
            value = self._options[name]
            if value is None or value == u'':
                raise KeyError
        except KeyError:
            if get_default:
                try:
                    value = self.arguments[name][u'default']
                except KeyError:
                    if name in range(self.positional):
                        return u''
            else:
                value = None
        return value

    def get_session_parameters(self):
        """Return a dictionary of parameters for the Session object"""
        if self.get('resume'):
            return {
                # override selected settings from command line
                'override_cas1': self.get('cas1', False),
                'override_mount': self.get(u'mount', False),
                # we always need to reset this or it may be a reference to an old device
                'override_current_device': self.get(u'current-device', True),
            }
        pcjr_term = self.get('pcjr-term')
        if pcjr_term and not os.path.exists(pcjr_term):
            pcjr_term = os.path.join(plat.info_dir, pcjr_term)
        if not os.path.exists(pcjr_term):
            pcjr_term = ''
        peek_values = {}
        try:
            for a in self.get('peek'):
                seg, addr, val = a.split(':')
                peek_values[int(seg)*0x10 + int(addr)] = int(val)
        except (TypeError, ValueError):
            pass
        device_params = {
                key.upper()+':' : self.get(key)
                for key in ('lpt1', 'lpt2', 'lpt3', 'com1', 'com2', 'cas1')}
        max_list = self.get('max-memory')
        max_list[1] = max_list[1]*16 if max_list[1] else max_list[0]
        max_list[0] = max_list[0] or max_list[1]
        return {
            'syntax': self.get('syntax'),
            'option_debug': self.get('debug'),
            'output_file': self.get(b'output'),
            'append': self.get(b'append'),
            'input_file': self.get(b'input'),
            'video_capabilities': self.get('video'),
            'codepage': self.get('codepage') or '437',
            'box_protect': not self.get('nobox'),
            'monitor': self.get('monitor'),
            # screen settings
            'screen_aspect': (3072, 2000) if self.get('video') == 'tandy' else (4, 3),
            'text_width': self.get('text-width'),
            'video_memory': self.get('video-memory'),
            'cga_low': self.get('cga-low'),
            'mono_tint': self.get('mono-tint'),
            'font': self.get('font'),
            # inserted keystrokes
            'keystring': self.get('keys').decode('string_escape').decode('utf-8'),
            # find program for PCjr TERM command
            'pcjr_term': pcjr_term,
            'option_shell': self.get('shell'),
            'double': self.get('double'),
            # device settings
            'device_params': device_params,
            'current_device': self.get(u'current-device'),
            'mount': self.get(u'mount'),
            'map_drives': self.get(u'map-drives'),
            'print_trigger': self.get('print-trigger'),
            'serial_buffer_size': self.get('serial-buffer-size'),
            # text file parameters
            'utf8': self.get('utf8'),
            'universal': not self.get('strict-newline'),
            # stdout echo (for filter interface)
            'echo_to_stdout': (self.get(b'interface') == u'none'),
            # keyboard settings
            'ignore_caps': not self.get('capture-caps'),
            'ctrl_c_is_break': self.get('ctrl-c-break'),
            # program parameters
            'max_list_line': 65535 if not self.get('strict-hidden-lines') else 65530,
            'allow_protect': self.get('strict-protect'),
            'allow_code_poke': self.get('allow-code-poke'),
            # max available memory to BASIC (set by /m)
            'max_memory': min(max_list) or 65534,
            # maximum record length (-s)
            'max_reclen': max(1, min(32767, self.get('max-reclen'))),
            # number of file records
            'max_files': self.get('max-files'),
            # first field buffer address (workspace size; 3429 for gw-basic)
            'reserved_memory': self.get('reserved-memory'),
        }

    def get_video_parameters(self):
        """Return a dictionary of parameters for the video plugin"""
        return {
            'force_display_size': self.get('dimensions'),
            'aspect': self.get('aspect'),
            'border_width': self.get('border'),
            'force_native_pixel': (self.get('scaling') == 'native'),
            'fullscreen': self.get('fullscreen'),
            'smooth': (self.get('scaling') == 'smooth'),
            'nokill': self.get('nokill'),
            'altgr': self.get('altgr'),
            'caption': self.get('caption'),
            'composite_monitor': (self.get('monitor') == 'composite'),
            'composite_card': self.get('video'),
            'copy_paste': self.get('copy-paste'),
            'pen': self.get('pen'),
            }

    def get_audio_parameters(self):
        """Return a dictionary of parameters for the audio plugin"""
        return {
            'nosound': self.get('nosound'),
            }

    def get_state_file(self):
        """Name of state file"""
        state_name = self.get('state') or 'PCBASIC.SAV'
        if os.path.exists(state_name):
            state_file = state_name
        else:
            state_file = os.path.join(plat.state_path, state_name)
        return state_file

    def get_interface(self):
        """Return name of interface plugin"""
        return self.get('interface') or 'graphical'

    def get_launch_parameters(self):
        """Return a dictionary of launch parameters"""
        run = (self.get(0) != '') or (self.get('run') != '')
        launch_params = {
            'quit': self.get('quit'),
            'wait': self.get('wait'),
            'cmd': self.get('exec'),
            'prog': self.get(0) or self.get('run') or self.get('load'),
            'run': run,
            'resume': self.get('resume'),
            # following GW, don't write greeting for redirected input
            # or command-line filter run
            'show_greeting': (not run and not self.get('exec') and
                not self.get('input') and not self.get('interface') == 'none'),
        }
        if self.get('resume'):
            launch_params['cmd'] = ''
            launch_params['run'] = False
        return launch_params

    def _get_arguments(self, argv):
        """Convert arguments to dictionary"""
        args = {}
        pos = 0
        for arg in argv:
            key, value = safe_split(arg, u'=')
            if key:
                if key[0:2] == u'--':
                    if key[2:]:
                        append_arg(args, key[2:], value)
                elif key[0] == u'-':
                    for i, short_arg in enumerate(key[1:]):
                        try:
                            skey, svalue = safe_split(self.short_args[short_arg], u'=')
                            if not svalue and not skey:
                                continue
                            if (not svalue) and i == len(key)-2:
                                # assign value to last argument specified
                                append_arg(args, skey, value)
                            else:
                                append_arg(args, skey, svalue)
                        except KeyError:
                            self._logger.warning(u'Ignored unrecognised option "-%s"', short_arg)
                elif pos < self.positional:
                    # positional argument
                    args[pos] = arg
                    pos += 1
                else:
                    self._logger.warning(u'Ignored extra positional argument "%s"', arg)
            else:
                self._logger.warning(u'Ignored unrecognised option "=%s"', value)
        return args

    def _parse_presets(self, remaining, conf_dict):
        """Parse presets"""
        presets = self.default_presets
        try:
            argdict = {u'preset': remaining.pop(u'preset')}
        except KeyError:
            argdict = {}
        # apply default presets, including nested presets
        while True:
            # get dictionary of default config
            for p in presets:
                try:
                    self._merge_arguments(argdict, conf_dict[p])
                except KeyError:
                    if p not in self.default_presets:
                        self._logger.warning(u'Ignored undefined preset "%s"', p)
            # look for more presets in expended arglist
            try:
                presets = self._parse_list(u'preset', argdict.pop(u'preset'))
            except KeyError:
                break
        return argdict

    def _parse_package(self, remaining):
        """Unpack BAZ package, if specified, and make its temp dir current"""
        # first positional arg: program or package name
        package = None
        try:
            arg_package = remaining[0]
        except KeyError:
            pass
        else:
            if os.path.isdir(arg_package):
                os.chdir(arg_package)
                remaining.pop(0)
                package = arg_package
            elif zipfile.is_zipfile(arg_package):
                remaining.pop(0)
                # extract the package to a temp directory
                # and make that the current dir for our run
                zipfile.ZipFile(arg_package).extractall(path=plat.temp_dir)
                os.chdir(plat.temp_dir)
                # if the zip-file contains only a directory at the top level,
                # then move into that directory. E.g. all files in package.zip
                # could be under the directory package/
                contents = os.listdir('.')
                if len(contents) == 1:
                    os.chdir(contents[0])
                # recursively rename all files to all-caps to avoid case issues on Unix
                # collisions: the last file renamed overwrites earlier ones
                for root, dirs, files in os.walk(u'.', topdown=False):
                    for name in dirs + files:
                        try:
                            os.rename(os.path.join(root, name),
                                      os.path.join(root, name.upper()))
                        except OSError:
                            # if we can't rename, ignore
                            pass
                package = arg_package
        # make package setting available
        return package

    def _parse_config(self, remaining):
        """Find the correct config file and read it"""
        # always read default config files; private config overrides system config
        # we update a whole preset at once, there's no joining of settings.
        conf_dict = self._read_config_file(self.system_config_path)
        conf_dict.update(self._read_config_file(self.user_config_path))
        # find any local overriding config file & read it
        config_file = None
        try:
            config_file = remaining.pop(u'config')
        except KeyError:
            if os.path.exists(self.config_name):
                config_file = self.config_name
        if config_file:
            conf_dict.update(self._read_config_file(config_file))
        return conf_dict

    def _read_config_file(self, config_file):
        """Read config file"""
        try:
            config = ConfigParser.RawConfigParser(allow_no_value=True)
            # use utf_8_sig to ignore a BOM if it's at the start of the file (e.g. created by Notepad)
            with codecs.open(config_file, b'r', b'utf_8_sig') as f:
                config.readfp(f)
        except (ConfigParser.Error, IOError):
            self._logger.warning(u'Error in configuration file %s. '
                           u'Configuration not loaded.', config_file)
            return {}
        presets = { header: dict(config.items(header))
                    for header in config.sections() }
        return presets

    def _parse_args(self, remaining):
        """Retrieve command line options"""
        # set arguments
        known = self.arguments.keys() + range(self.positional)
        args = {d:remaining[d] for d in remaining if d in known}
        not_recognised = {d:remaining[d] for d in remaining if d not in known}
        for d in not_recognised:
            self._logger.warning(u'Ignored unrecognised option "%s=%s"',
                            d, not_recognised[d])
        return args

    ################################################

    def _merge_arguments(self, args0, args1):
        """Update args0 with args1. Lists of indefinite length are appended"""
        for a in args1:
            try:
                if (a in args0 and self.arguments[a][u'list'] == u'*' and args0[a]):
                    args0[a] += u',' + args1[a]
                    continue
            except KeyError:
                pass
            # override
            args0[a] = args1[a]

    def _clean_arguments(self, args):
        """Convert arguments to required type and list length"""
        for d in args:
            try:
                args[d] = self._parse_list(d, args[d], self.arguments[d][u'list'])
            except KeyError:
                # not a list
                args[d] = self._parse_type(d, args[d])

    def _parse_type(self, d, arg):
        """Convert argument to required type"""
        if d not in self.arguments:
            return arg
        if u'choices' in self.arguments[d]:
            arg = arg.lower()
        if u'type' in self.arguments[d]:
            if (self.arguments[d][u'type'] == u'int'):
                arg = self._parse_int(d, arg)
            elif (self.arguments[d][u'type'] == u'bool'):
                arg = self._parse_bool(d, arg)
        if u'choices' in self.arguments[d]:
            if arg and arg not in self.arguments[d][u'choices']:
                self._logger.warning(u'Value "%s=%s" ignored; should be one of (%s)',
                                d, unicode(arg), u', '.join(self.arguments[d][u'choices']))
                arg = u''
        return arg

    def _parse_list(self, d, s, length='*'):
        """Convert list strings to typed lists"""
        lst = s.split(u',')
        if lst == [u'']:
            if length == '*':
                return []
            elif length < 0:
                return [None]*(-length)
            else:
                return None
        lst = [self._parse_type(d, arg) for arg in lst]
        # negative length: optional up-to
        if length < 0:
            lst += [None]*(-length-len(lst))
        if length != u'*' and (len(lst) > abs(length) or len(lst) < length):
            self._logger.warning(u'Option "%s=%s" ignored, should have %d elements',
                            d, s, abs(length))
        return lst

    def _parse_bool(self, d, s):
        """Parse bool option. Empty string (i.e. specified) means True"""
        if s == u'':
            return True
        try:
            if s.upper() in (u'YES', u'TRUE', u'ON', u'1'):
                return True
            elif s.upper() in (u'NO', u'FALSE', u'OFF', u'0'):
                return False
        except AttributeError:
            self._logger.warning(u'Option "%s=%s" ignored; should be a boolean', d, s)
            return None

    def _parse_int(self, d, s):
        """Parse int option provided as a one-element list of string"""
        if s:
            try:
                return int(s)
            except ValueError:
                self._logger.warning(u'Option "%s=%s" ignored; should be an integer', d, s)
        return None


    #########################################################

    def build_default_config_file(self, file_name):
        """Write a default config file"""
        header = (
        u"# PC-BASIC private configuration file.\n"
        u"# Edit this file to change your default settings or add presets.\n"
        u"# Changes to this file will not affect any other users of your computer.\n"
        u"\n"
        u"[pcbasic]\n"
        u"# Use the [pcbasic] section to specify options you want to be enabled by default.\n"
        u"# See the documentation or run pcbasic -h for a list of available options.\n"
        u"# for example (for version '%s'):\n" % plat.version)
        footer = (
        u"\n\n# To add presets, create a section header between brackets and put the \n"
        u"# options you need below it, like this:\n"
        u"# [your_preset]\n"
        u"# border=0\n"
        u"# \n"
        u"# You will then be able to load these options with --preset=your_preset.\n"
        u"# If you choose the same name as a system preset, PC-BASIC will use your\n"
        u"# options for that preset and not the system ones. This is not recommended.\n")
        argnames = sorted(self.arguments.keys())
        try:
            with open(file_name, b'w') as f:
                # write a BOM at start to ensure Notepad gets that it's utf-8
                # but don't use codecs.open as that doesn't do CRLF on Windows
                f.write(b'\xEF\xBB\xBF')
                f.write(header.encode(b'utf-8'))
                for a in argnames:
                    try:
                        # check if it's a list
                        self.arguments[a][u'list']
                        formatted = u','.join(map(unicode, self.arguments[a][u'default']))
                    except(KeyError, TypeError):
                        formatted = unicode(self.arguments[a][u'default'])
                    f.write((u'# %s=%s' % (a, formatted)).encode(b'utf-8'))
                    try:
                        f.write((u' ; choices: %s\n' %
                                    u', '.join(map(unicode, self.arguments[a][u'choices']))).encode(b'utf-8'))
                    except(KeyError, TypeError):
                        f.write(b'\n')
                f.write(footer)
        except (OSError, IOError):
            # can't create file, ignore. we'll get a message later.
            pass
