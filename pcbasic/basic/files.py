"""
PC-BASIC - files.py
Devices, Files and I/O operations

(c) 2013, 2014, 2015, 2016 Rob Hagemans
This file is released under the GNU GPL version 3 or later.
"""

import os
import sys
import string
import logging
import platform
import io

from . import error
from . import devices
from . import cassette
from . import disk
from . import ports
from . import values


# MS-DOS device files
device_files = ('AUX', 'CON', 'NUL', 'PRN')


############################################################################
# General file manipulation

class Files(object):
    """File manager."""

    def __init__(self, devices, max_files, max_reclen):
        """Initialise files."""
        self.files = {}
        self.max_files = max_files
        self.max_reclen = max_reclen
        self.devices = devices

    def close(self, num):
        """Close a numbered file."""
        try:
            self.files[num].close()
            del self.files[num]
        except KeyError:
            pass

    def close_all(self):
        """Close all files."""
        for f in self.files.values():
            f.close()
        self.files = {}

    reset_ = close_all

    def close_(self, number=None):
        """CLOSE: close a file, or all files."""
        if number is None:
            self.close_all()
        else:
            try:
                self.close(number)
            except KeyError:
                pass

    def open_(self, number, name, mode=None, reclen=None, access=None, lock=None):
        """OPEN: open a data file."""
        mode = mode or 'R'
        default_access_modes = {'I':'R', 'O':'W', 'A':'RW', 'R':'RW'}
        access = access or default_access_modes[mode]
        lock = lock or b''
        if reclen is None:
            reclen = 128
        # mode and access must match if not a RANDOM file
        # If FOR APPEND ACCESS WRITE is specified, raises PATH/FILE ACCESS ERROR
        # If FOR and ACCESS mismatch in other ways, raises SYNTAX ERROR.
        if mode == 'A' and access == 'W':
            raise error.RunError(error.PATH_FILE_ACCESS_ERROR)
        elif mode != 'R' and access and access != default_access_modes[mode]:
            raise error.RunError(error.STX)
        error.range_check(1, self.max_reclen, reclen)
        # can't open file 0, or beyond max_files
        error.range_check_err(1, self.max_files, number, error.BAD_FILE_NUMBER)
        self.open(number, name, 'D', mode, access, lock, reclen)

    def field_(self, the_file, name, index, offset, width):
        """FIELD: attach a fiedl variable."""
        the_file.field.attach_var(name, index, offset, width)

    def _set_record_pos(self, the_file, pos=None):
        """Helper function: PUT and GET syntax."""
        # for COM files
        num_bytes = the_file.reclen
        if pos is not None:
            # forcing to single before rounding - this means we don't have enough precision
            # to address each individual record close to the maximum record number
            # but that's in line with GW
            pos = values.round(values.csng_(pos)).to_value()
            # not 2^32-1 as the manual boasts!
            # pos-1 needs to fit in a single-precision mantissa
            error.range_check_err(1, 2**25, pos, err=error.BAD_RECORD_NUMBER)
            if not isinstance(the_file, ports.COMFile):
                the_file.set_pos(pos)
            else:
                num_bytes = pos
        return the_file, num_bytes

    def put_(self, the_file, pos=None):
        """PUT: write record to file."""
        thefile, num_bytes = self._set_record_pos(the_file, pos)
        thefile.put(num_bytes)

    def get_(self, the_file, pos=None):
        """GET: read record from file."""
        thefile, num_bytes = self._set_record_pos(the_file, pos)
        thefile.get(num_bytes)

    def _get_lock_limits(self, lock_start_rec, lock_stop_rec):
        """Get record lock limits."""
        if lock_start_rec is None:
            lock_start_rec = 1
        else:
            lock_start_rec = values.round(lock_start_rec).to_value()
        if lock_stop_rec is None:
            lock_stop_rec = lock_start_rec
        else:
            lock_stop_rec = values.round(lock_stop_rec).to_value()
        if lock_start_rec < 1 or lock_start_rec > 2**25-2 or lock_stop_rec < 1 or lock_stop_rec > 2**25-2:
            raise error.RunError(error.BAD_RECORD_NUMBER)
        return lock_start_rec, lock_stop_rec

    def lock_(self, thefile, lock_start_rec, lock_stop_rec):
        """LOCK: set file or record locks."""
        try:
            thefile.lock(*self._get_lock_limits(lock_start_rec, lock_stop_rec))
        except AttributeError:
            # not a disk file
            raise error.RunError(error.PERMISSION_DENIED)

    def unlock_(self, thefile, lock_start_rec, lock_stop_rec):
        """UNLOCK: set file or record locks."""
        try:
            thefile.unlock(*self._get_lock_limits(lock_start_rec, lock_stop_rec))
        except AttributeError:
            # not a disk file
            raise error.RunError(error.PERMISSION_DENIED)

    def ioctl_statement_(self, thefile, control_string):
        """IOCTL: send control string to I/O device. Not implemented."""
        logging.warning("IOCTL statement not implemented.")
        raise error.RunError(error.IFC)

    def open(self, number, description, filetype, mode='I', access='R', lock='',
                  reclen=128, seg=0, offset=0, length=0):
        """Open a file on a device specified by description."""
        if (not description) or (number < 0) or (number > self.max_files):
            # bad file number; also for name='', for some reason
            raise error.RunError(error.BAD_FILE_NUMBER)
        if number in self.files:
            raise error.RunError(error.FILE_ALREADY_OPEN)
        name, mode = str(description), mode.upper()
        inst = None
        split_colon = name.split(':')
        if len(split_colon) > 1: # : found
            dev_name = split_colon[0].upper() + ':'
            dev_param = ''.join(split_colon[1:])
            try:
                device = self.devices.devices[dev_name]
            except KeyError:
                # not an allowable device or drive name
                # bad file number, for some reason
                raise error.RunError(error.BAD_FILE_NUMBER)
        else:
            device = self.devices.devices[self.devices.current_device + b':']
            # MS-DOS device aliases - these can't be names of disk files
            if device != self.devices.devices['CAS1:'] and name in device_files:
                if name == 'AUX':
                    device, dev_param = self.devices.devices['COM1:'], ''
                elif name == 'CON' and mode == 'I':
                    device, dev_param = self.devices.devices['KYBD:'], ''
                elif name == 'CON' and mode == 'O':
                    device, dev_param = self.devices.devices['SCRN:'], ''
                elif name == 'PRN':
                    device, dev_param = self.devices.devices['LPT1:'], ''
                elif name == 'NUL':
                    device, dev_param = devices.NullDevice(), ''
            else:
                # open file on default device
                dev_param = name
        # open the file on the device
        new_file = device.open(number, dev_param, filetype, mode, access, lock,
                               reclen, seg, offset, length)
        if number:
            self.files[number] = new_file
        return new_file

    def open_native_or_basic(self, filespec, filetype, mode):
        """If the specified file exists, open it; if not, try as BASIC file spec. Do not register in files dict."""
        if not filespec:
            return self._open_stdio(filetype, mode)
        try:
            # first try exact file name
            return self.devices.internal_disk.create_file_object(
                    open(os.path.expandvars(os.path.expanduser(filespec)),
                         self.devices.internal_disk.access_modes[mode]),
                    filetype, mode)
        except EnvironmentError as e:
            # otherwise, accept capitalised versions and default extension
            return self.open(0, filespec, filetype, mode)

    def _open_null(self, filetype, mode):
        """Open a null file object. Do not register in files dict."""
        return devices.TextFileBase(devices.nullstream(), filetype, mode)

    def _open_stdio(self, filetype, mode):
        """Open a file object on standard IO. Do not register in files dict."""
        # OS-specific stdin/stdout selection
        # no stdin/stdout access allowed on packaged apps in OSX
        if platform.system() == b'Darwin':
            return self._open_null(filetype, mode)
        try:
            if mode == 'I':
                # use io.BytesIO buffer for seekability
                in_buffer = io.BytesIO(sys.stdin.read())
                return self.devices.internal_disk.create_file_object(in_buffer, filetype, mode)
            else:
                return self.devices.internal_disk.create_file_object(sys.stdout, filetype, mode)
        except EnvironmentError as e:
            logging.warning('Could not open standard I/O: %s', e)
            return self._open_null(filetype, mode)

    def get(self, num, mode='IOAR', not_open=error.BAD_FILE_NUMBER):
        """Get the file object for a file number and check allowed mode."""
        if (num < 1):
            raise error.RunError(error.BAD_FILE_NUMBER)
        try:
            the_file = self.files[num]
        except KeyError:
            raise error.RunError(not_open)
        if the_file.mode.upper() not in mode:
            raise error.RunError(error.BAD_FILE_MODE)
        return the_file

    def _get_from_integer(self, num, mode='IOAR'):
        """Get the file object for an Integer file number and check allowed mode."""
        num = values.to_int(num, unsigned=True)
        error.range_check(0, 255, num)
        return self.get(num, mode)

    def loc_(self, num):
        """LOC: get file pointer."""
        return self._get_from_integer(num).loc()

    def eof_(self, num):
        """EOF: get end-of-file."""
        if num.is_zero():
            return False
        return -1 if self._get_from_integer(num, 'IR').eof() else 0

    def lof_(self, num):
        """LOF: get length of file."""
        return self._get_from_integer(num).lof()

    def lpos_(self, num):
        """LPOS: get the current printer column."""
        num = values.to_int(num)
        error.range_check(0, 3, num)
        printer = self.devices['LPT' + max(1, num) + ':']
        if printer.device_file:
            return printer.device_file.col
        return 1

    def ioctl_(self, infile):
        """IOCTL$: read device control string response; not implemented."""
        logging.warning("IOCTL$ function not implemented.")
        raise error.RunError(error.IFC)

    def input_(self, file_obj, num_chars):
        """INPUT$: read num chars from file."""
        if file_obj is None:
            file_obj = self.devices.kybd_file
        return file_obj.input_(num_chars)

    def write_(self, args):
        """WRITE: Output machine-readable expressions to the screen or a file."""
        file_number = next(args)
        if file_number is None:
            output = self.devices.scrn_file
        else:
            output = self.get(file_number, 'OAR')
        outstrs = []
        try:
            for expr in args:
                if isinstance(expr, values.String):
                    outstrs.append('"%s"' % expr.to_str())
                else:
                    outstrs.append(values.to_repr(expr, leading_space=False, type_sign=False))
        except error.RunError:
            if outstrs:
                output.write(','.join(outstrs) + ',')
            raise
        else:
            # write the whole thing as one thing (this affects line breaks)
            output.write_line(','.join(outstrs))


###############################################################################
# device management

class Devices(object):
    """Device manager."""

    # allowable drive letters in GW-BASIC are letters or @
    drive_letters = b'@' + string.ascii_uppercase

    def __init__(self, events, fields, screen, keyboard,
                device_params, current_device, mount_dict,
                print_trigger, temp_dir, serial_in_size, utf8, universal):
        """Initialise devices."""
        self.devices = {}
        # screen device
        self._screen = screen
        self.devices['SCRN:'] = devices.SCRNDevice(screen)
        # KYBD: device needs screen as it can set the screen width
        self.devices['KYBD:'] = devices.KYBDDevice(keyboard, screen)
        self.scrn_file = self.devices['SCRN:'].device_file
        self.kybd_file = self.devices['KYBD:'].device_file
        self.codepage = screen.codepage
        # ports
        # parallel devices - LPT1: must always be defined
        if not device_params:
            device_params = {'LPT1:': '', 'LPT2:': '', 'LPT3:': '', 'COM1:': '', 'COM2:': '', 'CAS1:': ''}
        self.devices['LPT1:'] = ports.LPTDevice(device_params['LPT1:'], devices.nullstream(), print_trigger, self.codepage, temp_dir)
        self.devices['LPT2:'] = ports.LPTDevice(device_params['LPT2:'], None, print_trigger, self.codepage, temp_dir)
        self.devices['LPT3:'] = ports.LPTDevice(device_params['LPT3:'], None, print_trigger, self.codepage, temp_dir)
        self.lpt1_file = self.devices['LPT1:'].device_file
        # serial devices
        # buffer sizes (/c switch in GW-BASIC)
        self.devices['COM1:'] = ports.COMDevice(device_params['COM1:'], events, devices.Field(serial_in_size), serial_in_size)
        self.devices['COM2:'] = ports.COMDevice(device_params['COM2:'], events, devices.Field(serial_in_size), serial_in_size)
        # cassette
        # needs a screen for write() and write_line() to display Found and Skipped messages on opening files
        self.devices['CAS1:'] = cassette.CASDevice(device_params['CAS1:'], screen)
        # disk file locks
        self.locks = disk.Locks()
        # field buffers
        self.fields = fields
        # for wait()
        self.events = events
        # text file settings
        self.utf8 = utf8
        self.universal = universal
        # disk devices
        self.internal_disk = disk.DiskDevice(b'', None, u'',
                        self.fields, self.locks, self.codepage, self.events, self.utf8, self.universal)
        for letter in self.drive_letters:
            if not mount_dict:
                mount_dict = {}
            if letter in mount_dict:
                self.devices[letter + b':'] = disk.DiskDevice(letter, mount_dict[letter][0], mount_dict[letter][1],
                            self.fields, self.locks, self.codepage, self.events, self.utf8, self.universal)
            else:
                self.devices[letter + b':'] = disk.DiskDevice(letter, None, u'',
                                self.fields, self.locks, self.codepage, self.events, self.utf8, self.universal)
        self.current_device = current_device.upper()

    def close(self):
        """Close device master files."""
        for d in self.devices.values():
            d.close()

    def get_diskdevice_and_path(self, path):
        """Return the disk device and remaining path for given file spec."""
        # careful - do not convert path to uppercase, we still need to match
        splits = bytes(path).split(b':', 1)
        if len(splits) == 0:
            dev, spec = self.current_device, b''
        elif len(splits) == 1:
            dev, spec = self.current_device, splits[0]
        else:
            try:
                dev, spec = splits[0].upper(), splits[1]
            except KeyError:
                raise error.RunError(error.DEVICE_UNAVAILABLE)
        # must be a disk device
        if dev not in self.drive_letters:
            raise error.RunError(error.DEVICE_UNAVAILABLE)
        return self.devices[dev + b':'], spec

    ###########################################################################
    # function callbacks

    def erdev_(self):
        """ERDEV: device error value; not implemented."""
        logging.warning('ERDEV function not implemented.')
        return 0

    def erdev_str_(self):
        """ERDEV$: device error string; not implemented."""
        logging.warning('ERDEV$ function not implemented.')
        return b''

    def exterr_(self, val):
        """EXTERR: device error information; not implemented."""
        logging.warning('EXTERR function not implemented.')
        error.range_check(0, 3, values.to_int(val))
        return 0

    ###########################################################################
    # statement callbacks

    def motor_(self, value):
        """MOTOR: drive cassette motor; not implemented."""
        logging.warning('MOTOR statement not implemented.')

    def lcopy_(self, val):
        """LCOPY: screen copy / no-op in later GW-BASIC."""
        # See e.g. http://shadowsshot.ho.ua/docs001.htm#LCOPY

    def chdir_(self, name):
        """CHDIR: change working directory."""
        dev, path = self.get_diskdevice_and_path(name)
        dev.chdir(path)

    def mkdir_(self, name):
        """MKDIR: create directory."""
        dev, path = self.get_diskdevice_and_path(name)
        dev.mkdir(path)

    def rmdir_(self, name):
        """RMDIR: remove directory."""
        dev, path = self.get_diskdevice_and_path(name)
        dev.rmdir(path)

    def name_(self, oldname, newname):
        """NAME: rename file or directory."""
        dev, oldpath = self.get_diskdevice_and_path(oldname)
        newdev, newpath = self.get_diskdevice_and_path(newname)
        # don't rename open files
        dev.check_file_not_open(oldpath)
        if dev != newdev:
            raise error.RunError(error.RENAME_ACROSS_DISKS)
        dev.rename(oldpath, newpath)

    def kill_(self, name):
        """KILL: remove file."""
        dev, path = self.get_diskdevice_and_path(name)
        # don't delete open files
        dev.check_file_not_open(path)
        dev.kill(path)

    def files_(self, pathmask=None):
        """FILES: output directory listing to screen."""
        # pathmask may be left unspecified, but not empty
        if pathmask == b'':
            raise error.RunError(error.BAD_FILE_NAME)
        elif pathmask is None:
            pathmask = b''
        dev, path = self.get_diskdevice_and_path(pathmask)
        dev.files(self._screen, path)
