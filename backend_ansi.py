#
# PC-BASIC 3.23 - backend_ansi.py
#
# ANSI backend for Console
#
# (c) 2013 Rob Hagemans 
#
# This file is released under the GNU GPL version 3. 
# please see text file COPYING for licence terms.
#

## implements text screen I/O functions on an ANSI/AIX terminal
# using raw escape sequences (as curses module doesn't do UTF8 it seems)

# silent get character with no enter,  using raw terminal
# raw terminal, see http://stackoverflow.com/questions/1052107/reading-a-single-character-wait_char-style-in-python-is-not-working-in-unix
# non-blocking input with select, see http://repolinux.wordpress.com/2012/10/09/non-blocking-read-from-stdin-in-python/ 
# reading escape sequences with os.read, see http://stackoverflow.com/questions/8620878/check-for-extra-characters-in-linux-terminal-buffer

import time
import sys, tty, termios, select
import os
import sys

import unicodepage
import error
import console

term_echo_on = True
term_attr = None
term = sys.stdout

# black, blue, green, cyan, red, magenta, yellow, white
colours = (0, 4, 2, 6, 1, 5, 3, 7)
colournames = ('Black','Dark Blue','Dark Green','Dark Cyan','Dark Red','Dark Magenta','Brown','Light Gray',
'Dark Gray','Blue','Green','Cyan','Red','Magenta','Yellow','White')

# ANSI escape sequences
# for reference, see:
# http://en.wikipedia.org/wiki/ANSI_escape_code
# http://misc.flogisoft.com/bash/tip_colors_and_formatting

esc_reset = '\x1b[0m\x1bc'
esc_set_scroll_screen = '\x1b[r'
esc_set_scroll_region = '\x1b[%i;%ir'
esc_clear_screen = '\x1b[2J'
esc_clear_line = '\x1b[2K'
esc_scroll_up = '\x1b[%iS'
esc_scroll_down = '\x1b[%iT'
esc_show_cursor = '\x1b[?25h'
esc_hide_cursor = '\x1b[?25l'
esc_resize_term = '\x1b[8;%i;%i;t'
esc_move_cursor = '\x1b[%i;%if' 
esc_save_cursor_pos = '\x1b[s'
esc_restore_cursor_pos = '\x1b[u'
esc_request_size = '\x1b[18;t'
esc_set_cursor_colour = '\x1b]12;%s\x07'
esc_set_cursor_shape = '\x1b[%i q'  #% (2*(is_line+1) - blinks)    # 1 blinking block 2 block 3 blinking line 4 line
esc_set_colour = '\x1b[%im'      

# escape sequence to scancode dictionary
# for scan codes, see e.g. http://www.antonis.de/qbebooks/gwbasman/appendix%20h.html
esc_to_scan = {
    '\x1b\x4f\x50': '\x00\x3b', # F1
    '\x1b\x4f\x51': '\x00\x3c', # F2
    '\x1b\x4f\x52': '\x00\x3d', # F3
    '\x1b\x4f\x53': '\x00\x3e', # F4
    '\x1b\x5b\x31\x35\x7e':  '\x00\x3f', # F5
    '\x1b\x5b\x31\x37\x7e':  '\x00\x40', # F6
    '\x1b\x5b\x31\x38\x7e':  '\x00\x41', # F7
    '\x1b\x5b\x31\x39\x7e':  '\x00\x42', # F8
    '\x1b\x5b\x32\x30\x7e':  '\x00\x43', # F9
    '\x1b\x5b\x32\x31\x7e':  '\x00\x44', # F10
    '\x1b\x4f\x46': '\x00\x4F', # END
    '\x1b\x4f\x48': '\x00\x47', # HOME
    '\x1b\x5b\x41': '\x00\x48', # arrow up
    '\x1b\x5b\x42': '\x00\x50', # arrow down
    '\x1b\x5b\x43': '\x00\x4d', # arrow right
    '\x1b\x5b\x44': '\x00\x4b', # arrow left
    '\x1b\x5b\x32\x7e': '\x00\x52', # INS
    '\x1b\x5b\x33\x7e': '\x00\x53', # DEL
    '\x1b\x5b\x35\x7e': '\x00\x49', # PG UP
    '\x1b\x5b\x36\x7e': '\x00\x51', # PG DN
    # this is not an esc sequence, but UTF-8 for GBP symbol
    '\xc2\xa3': '\x9c'  # pound sterling symbol
}
 
def get_size():
    sys.stdout.write(esc_request_size)
    sys.stdout.flush()
    # Read response one char at a time until 't'
    resp = char = ""
    while char != 't':
        char = sys.stdin.read(1)
        resp += char
    return resp[4:-1].split(';')

######

def init():
    # see if the resize has worked; if not, allowWindowOps needs to be enabled
    term_echo(False)
    term.write(esc_resize_term % (25, 80))
    term.flush()
    return True
    
def init_screen_mode(mode, new_font_height):
    if mode != 0:
        raise error.RunError(5)
    
def setup_screen(height, width):
    set_palette()
    term.write(esc_clear_screen)
    term.write(esc_resize_term % (height, width))
    term.flush()
    
def close():
    term_echo()
    build_line_cursor(True)
    term.write(esc_show_cursor)
    term.write(esc_clear_screen)
    term.write(esc_reset)
    term.flush()

def idle():
    time.sleep(0.024)
    
######

def clear_rows(bg, start, stop):
    for r in range(start, stop+1):
        term.write(esc_move_cursor % (r, 1))    
        term.write(esc_clear_line)
    term.write(esc_move_cursor % (console.row, console.col))
    term.flush()

def redraw():
   for y in range(console.height):
        console.redraw_row(0, y+1)

#####

def set_palette(new_palette=None):
    global palette
    palette = new_palette if new_palette else list(range(16)) 
    redraw()
    
def set_palette_entry(index, colour):
    global palette
    palette[index] = colour
    redraw()
    
def get_palette_entry(index):
    return palette[index]

####

def set_cursor_colour(color):
    term.write(esc_set_cursor_colour % colournames[apply_palette(color)%16])
    term.flush()
    
def show_cursor(do_show, prev):
    term.write(esc_show_cursor if do_show else esc_hide_cursor)
    term.flush()

def check_events():
    check_keyboard()
    if console.cursor:
        term.write(esc_move_cursor % (console.row,console.col))
        term.flush()
        
def apply_palette(colour):
    return colour&0x8 | palette[colour&0x7]

last_attr = None
def set_attr(attr):
    global last_attr
    if attr == last_attr:
        return
    term.write(esc_set_colour % 0) 
    if attr & 0x80:
        # blink
        term.write(esc_set_colour % 5)   
    fore, back = apply_palette(attr & 0xf), apply_palette((attr>>4) & 0x7)
    if (fore%16)<8:
        term.write(esc_set_colour % (30+colours[fore%8]))
    else:
        term.write(esc_set_colour % (90+colours[fore%8]))       
    term.write(esc_set_colour % (40+colours[back%8]))
    term.write(esc_set_cursor_colour % colournames[fore%16])
    term.flush()  
    last_attr = attr

def putc_at(row, col, c):
    term.write(esc_move_cursor % (row, col))
    term.write(unicodepage.to_utf8(c))
    term.flush()
   
def scroll(from_line):
    term.write(esc_set_scroll_region % (from_line, console.scroll_height))
    term.write(esc_scroll_up % 1)
    term.write(esc_set_scroll_screen)
    if console.row > 0:
        term.write(esc_move_cursor % (console.row-1, console.col))
    term.flush()
    
def scroll_down(from_line):
    term.write(esc_set_scroll_region % (from_line, console.scroll_height))
    term.write(esc_scroll_down % 1)
    term.write(esc_set_scroll_screen)
    if console.row < console.height:
        term.write(esc_move_cursor % (console.row+1, console.col))
    term.flush()

#######

def term_echo(on=True):
    global term_attr, term_echo_on
    # sets raw terminal - no echo, by the character rather than by the line
    fd = sys.stdin.fileno()
    if (not on) and term_echo_on:
        term_attr = termios.tcgetattr(fd)
        tty.setraw(fd)
    elif not term_echo_on and term_attr != None:
        termios.tcsetattr(fd, termios.TCSADRAIN, term_attr)
    previous = term_echo_on
    term_echo_on = on    
    return previous

def check_keyboard():
    fd = sys.stdin.fileno()
    c = ''
    # check if stdin has characters to read
    d = select.select([sys.stdin], [], [], 0) 
    # longest escape sequence I use is 5 bytes
    if d[0] != []:
        c = os.read(fd,5)
    # handle key
    if c == '':
        pass
    elif c == '\x03': # ctrl-C
        raise error.Break() 
    elif c == '\x00':      # to avoid confusion with scancodes
        console.insert_key('\x00\x00')      
    elif c == '\x7f':      # backspace
        console.insert_key('\x08')
    else:
        try:
            console.insert_key(esc_to_scan[c])       
        except KeyError:
            # all other codes are chopped off, 
            # so other escape sequences will register as an escape keypress.
            console.insert_key(c[0])    
        
########

def debug_print(s):
    # rpint to screen as normal, to avoid corrupting the screen by using stderr
    console.write(s)

def copy_page(src, dst):
    pass
        
def build_line_cursor( is_line):
    # works on xterm, not on xfce
    # on xfce, gibberish is printed
    #term.write(esc_set_cursor_shape % 2*(is_line+1) - 1)
    pass
    
def build_shape_cursor(from_line, to_line):
    pass

# no pen, stick

def get_pen(fn):
    # fn 6,7,8,9 refer to character coordinates, 0 not allowed
    return 1 if fn >= 6 else 0 

def get_stick(fn):
    return 0
  
def get_strig(fn):
    return False 
    
