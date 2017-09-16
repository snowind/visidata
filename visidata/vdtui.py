#!/usr/bin/env python3
#
# Copyright 2017 Saul Pwanson  http://saul.pw/vdtui
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:

# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.

# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
#

'vdtui: a curses framework for columnar data'

# Just include this whole file in your project as-is.  If you do make
# modifications, please keep the base vdtui version and append your own id and
# version.
__version__ = 'saul.pw/vdtui v0.97pre'
__author__ = 'Saul Pwanson <vdtui@saul.pw>'
__license__ = 'MIT'
__status__ = 'Beta'

from builtins import *
import sys
import os
import os.path
import collections
from copy import copy, deepcopy
import curses
import datetime
import functools
import gzip
import io
import itertools
import string
import re
import textwrap
import threading
import time

class EscapeException(Exception):
    pass

baseCommands = collections.OrderedDict()
baseOptions = collections.OrderedDict()

def Command(keystrokes, execstr, helpstr):
    return (keystrokes, helpstr, execstr)

def _registerCommand(cmddict, keystrokes, execstr, helpstr):
    if isinstance(keystrokes, str):
        keystrokes = [keystrokes]

    for ks in keystrokes:
        cmddict[ks] = (ks, helpstr, execstr)

def globalCommand(keystrokes, execstr, helpstr):
    _registerCommand(baseCommands, keystrokes, execstr, helpstr)

def alias(new, existing):
    _, helpstr, execstr = baseCommands[existing]
    globalCommand(new, execstr, helpstr)


class configbool:
    def __init__(self, v):
        if isinstance(v, str):
            self.val = v and (v[0] not in "0fFnN")
        else:
            self.val = bool(v)

    def __bool__(self):
        return self.val

    def __str__(self):
        return str(self.val)

configbool.__name__ = 'bool'

def option(name, default, helpstr=''):
    if isinstance(default, bool):
        default = configbool(default)

    baseOptions[name] = [name, default, default, helpstr]  # see OptionsObject

theme = option

class OptionsObject:
    'minimalist options framework'
    def __init__(self, d):
        object.__setattr__(self, '_opts', d)

    def __getattr__(self, k):
        name, value, default, helpstr = self._opts[k]
        return value

    def __setattr__(self, k, v):
        self.__setitem__(k, v)

    def __setitem__(self, k, v):
        if k not in self._opts:
            raise Exception('no such option "%s"' % k)
        self._opts[k][1] = type(self._opts[k][1])(v)

options = OptionsObject(baseOptions)


option('debug', False, 'abort on error and display stacktrace')
option('readonly', False, 'disable saving')

option('encoding', 'utf-8', 'as passed to codecs.open')
option('encoding_errors', 'surrogateescape', 'as passed to codecs.open')

option('curses_timeout', 100, 'curses timeout in ms')

option('default_width', 20, 'default column width')
option('regex_flags', 'I', 'flags to pass to re.compile() [AILMSUX]')
option('num_colors', 0, 'force number of colors to use')
option('textwrap', True, 'wrap text to fit window width on TextSheet')

option('cmd_after_edit', 'j', 'command keystroke to execute after successful edit')
option('aggr_null_filter', 'none', 'invalid values to filter out when aggregating: (n/e/f/"")')
option('force_valid_colnames', False, 'clean column names to be valid Python identifiers')

theme('disp_truncator', '…')
theme('disp_key_sep', '/')
theme('disp_format_exc', '?')
theme('disp_getter_exc', '!')
theme('disp_edit_fill', '_', 'edit field fill character')
theme('disp_more_left', '<', 'display cue in header indicating more columns to the left')
theme('disp_more_right', '>', 'display cue in header indicating more columns to the right')
theme('disp_column_sep', '|', 'chars between columns')
theme('disp_keycol_sep', '\u2016', 'chars between keys and rest of columns')

theme('disp_error_val', '¿', 'displayed contents when getter fails due to exception')
theme('disp_none', '',  'visible contents of a cell whose value was None')
theme('color_type_note', '226 green', 'for the type annotation on cells in anytype columns')
theme('color_current_row', 'reverse')
theme('color_default', 'normal')
theme('color_selected_row', '215 yellow')
theme('color_format_exc', '48 bold yellow')
theme('color_getter_exc', 'red bold')
theme('color_current_col', 'bold')
theme('color_current_hdr', 'reverse underline')
theme('color_key_col', '81 cyan')
theme('color_default_hdr', 'bold underline')
theme('color_column_sep', '246 blue')
theme('disp_status_sep', ' | ', 'string separating multiple statuses')
theme('disp_unprintable', '.', 'a substitute character for unprintables')
theme('disp_column_fill', ' ', 'pad chars after column value')
theme('disp_oddspace', '\u00b7', 'displayable character for odd whitespace')
theme('color_status', 'bold', 'status line color')
theme('color_edit_cell', 'normal', 'edit cell color')
theme('disp_status_fmt', '{sheet.name}| ', 'status line prefix')
theme('disp_ambig_width', 1, 'width to use for unicode chars marked ambiguous')

ENTER='^J'
ESC='^['

globalCommand('q',  'vd.sheets.pop(0)', 'quit the current sheet')

globalCommand(['h', 'KEY_LEFT'],  'cursorRight(-1)', 'go one column left')
globalCommand(['j', 'KEY_DOWN'],  'cursorDown(+1)', 'go one row down')
globalCommand(['k', 'KEY_UP'],    'cursorDown(-1)', 'go one row up')
globalCommand(['l', 'KEY_RIGHT'], 'cursorRight(+1)', 'go one column right')
globalCommand(['^F', 'KEY_NPAGE', 'kDOWN'], 'cursorDown(nVisibleRows); sheet.topRowIndex += nVisibleRows', 'scroll one page down')
globalCommand(['^B', 'KEY_PPAGE', 'kUP'], 'cursorDown(-nVisibleRows); sheet.topRowIndex -= nVisibleRows', 'scroll one page up')

globalCommand('gq', 'vd.sheets.clear()', 'drop all sheets (clean exit)')

globalCommand('gh', 'sheet.cursorVisibleColIndex = sheet.leftVisibleColIndex = 0', 'go to leftmost column')
globalCommand('gk', 'sheet.cursorRowIndex = sheet.topRowIndex = 0', 'go to top row')
globalCommand('gj', 'sheet.cursorRowIndex = len(rows); sheet.topRowIndex = cursorRowIndex-nVisibleRows', 'go to bottom row')
globalCommand('gl', 'sheet.cursorVisibleColIndex = len(visibleCols)-1', 'go to rightmost column')

alias('gg', 'gk')
alias('G', 'gj')
alias('KEY_HOME', 'gk')
alias('KEY_END', 'gj')

globalCommand('^L', 'vd.scr.clear()', 'redraw entire terminal screen')
globalCommand('^G', 'status(statusLine)', 'show info for the current sheet')
globalCommand('^V', 'status(__version__)', 'show version information')
globalCommand('^P', 'vd.push(TextSheet("statusHistory", vd.statusHistory))', 'open sheet with all previous status messages')

globalCommand('<', 'moveToNextRow(lambda row,sheet=sheet,col=cursorCol,val=cursorValue: col.getValue(row) != val, reverse=True) or status("no different value up this column")', 'move up to previous value in this column')
globalCommand('>', 'moveToNextRow(lambda row,sheet=sheet,col=cursorCol,val=cursorValue: col.getValue(row) != val) or status("no different value down this column")', 'move down to next value in this column')
globalCommand('{', 'moveToNextRow(lambda row,sheet=sheet: sheet.isSelected(row), reverse=True) or status("no previous selected row")', 'move to previous selected row')
globalCommand('}', 'moveToNextRow(lambda row,sheet=sheet: sheet.isSelected(row)) or status("no next selected row")', 'move to next selected row')

globalCommand('_', 'cursorCol.toggleWidth(cursorCol.getMaxWidth(visibleRows))', 'toggle this column width between default_width and to fit visible values')
globalCommand('-', 'cursorCol.width = 0', 'hide this column')
globalCommand('!', 'toggleKeyColumn(cursorColIndex)', 'toggle this column as a key column')
globalCommand('~', 'cursorCol.type = str', 'set column type to string')
globalCommand('@', 'cursorCol.type = date', 'set column type to ISO8601 datetime')
globalCommand('#', 'cursorCol.type = int', 'set column type to integer')
globalCommand('$', 'cursorCol.type = currency', 'set column type to currency')
globalCommand('%', 'cursorCol.type = float', 'set column type to float')
globalCommand('^', 'cursorCol.name = editCell(cursorVisibleColIndex, -1)', 'rename this column')

globalCommand('g_', 'for c in visibleCols: c.width = c.getMaxWidth(visibleRows)', 'set width of all columns to fit visible cells')

globalCommand('[', 'rows.sort(key=lambda r,col=cursorCol: col.getTypedValue(r))', 'sort by this column ascending')
globalCommand(']', 'rows.sort(key=lambda r,col=cursorCol: col.getTypedValue(r), reverse=True)', 'sort by this column descending')
globalCommand('g[', 'rows.sort(key=lambda r,cols=keyCols: tuple(c.getTypedValue(r) for c in cols))', 'sort by all key columns ascending')
globalCommand('g]', 'rows.sort(key=lambda r,cols=keyCols: tuple(c.getTypedValue(r) for c in cols), reverse=True)', 'sort by all key columns descending')

globalCommand('^E', 'vd.lastErrors and vd.push(TextSheet("last_error", vd.lastErrors[-1])) or status("no error")', 'open stack trace for most recent error')
globalCommand('z^E', 'vd.push(TextSheet("cell_error", getattr(cursorCell, "error") or error("no error this cell")))', 'open stack trace for most recent error')


globalCommand('^^', 'vd.sheets[0], vd.sheets[1] = vd.sheets[1], vd.sheets[0]', 'jump to previous sheet')

globalCommand('g^E', 'vd.push(TextSheet("last_errors", "\\n\\n".join(vd.lastErrors)))', 'open most recent errors')

globalCommand('^R', 'reload(); recalc(); status("reloaded")', 'reload sheet from source')
globalCommand('z^R', 'cursorCol._cachedValues.clear()', 'clear cache on this column')

globalCommand('/', 'moveRegex(regex=input("/", type="regex"), columns="cursorCol", backward=False)', 'search this column forward for regex')
globalCommand('?', 'moveRegex(regex=input("?", type="regex"), columns="cursorCol", backward=True)', 'search this column backward for regex')
globalCommand('n', 'moveRegex(reverse=False)', 'go to next match')
globalCommand('N', 'moveRegex(reverse=True)', 'go to previous match')

globalCommand('g/', 'moveRegex(regex=input("g/", type="regex"), backward=False, columns="visibleCols")', 'search regex forward in all visible columns')
globalCommand('g?', 'moveRegex(regex=input("g?", type="regex"), backward=True, columns="visibleCols")', 'search regex backward in all visible columns')

globalCommand('e', 'cursorCol.setValues([cursorRow], editCell(cursorVisibleColIndex)); sheet.exec_keystrokes(options.cmd_after_edit)', 'edit this cell')
globalCommand('ge', 'cursorCol.setValues(selectedRows or rows, input("set selected to: ", value=cursorValue))', 'edit this column for all selected rows')
globalCommand('zd', 'cursorCol.setValues([cursorRow], None)', 'set this cell to None')
globalCommand('gzd', 'cursorCol.setValues(selectedRows, None)', 'set this column to None for all selected rows')
alias('KEY_DC', 'zd')
alias('gKEY_DC', 'gzd')

globalCommand('t', 'toggle([cursorRow]); cursorDown(1)', 'toggle select of this row')
globalCommand('s', 'select([cursorRow]); cursorDown(1)', 'select this row')
globalCommand('u', 'unselect([cursorRow]); cursorDown(1)', 'unselect this row')

globalCommand('|', 'selectByIdx(searchRegex(regex=input("|", type="regex"), columns="cursorCol"))', 'select rows by regex matching this columns')
globalCommand('\\', 'unselectByIdx(searchRegex(regex=input("\\\\", type="regex"), columns="cursorCol"))', 'unselect rows by regex matching this columns')

globalCommand('gt', 'toggle(rows)', 'toggle select of all rows')
globalCommand('gs', 'select(rows)', 'select all rows')
globalCommand('gu', '_selectedRows.clear()', 'unselect all rows')

globalCommand('g|', 'selectByIdx(searchRegex(regex=input("g|", type="regex"), columns="visibleCols"))', 'select rows by regex matching any visible column')
globalCommand('g\\', 'unselectByIdx(searchRegex(regex=input("g\\\\", type="regex"), columns="visibleCols"))', 'unselect rows by regex matching any visible column')

globalCommand(',', 'select(gatherBy(lambda r,c=cursorCol,v=cursorValue: c.getValue(r) == v), progress=False)', 'select rows matching by this column')
globalCommand('g,', 'select(gatherBy(lambda r,v=cursorRow: r == v), progress=False)', 'select all rows that match this row')

globalCommand('"', 'vs = copy(sheet); vs.name += "_selectedref"; vs.rows = list(selectedRows or rows); vd.push(vs)', 'push duplicate sheet with refs to selected or all rows')
globalCommand('g"', 'vs = deepcopy(sheet); vs.name += "_selectedcopy"; vs.rows = deepcopy(selectedRows or rows); vd.push(vs); status("pushed sheet with deepcopy of all rows")', 'push duplicate sheet with copies of selected or all rows')

globalCommand('=', 'addColumn(ColumnExpr(input("new column expr=", "expr")), index=cursorColIndex+1)', 'add column by expr')
globalCommand('g=', 'cursorCol.setValuesFromExpr(selectedRows or rows, input("set selected=", "expr"))', 'set this column in selected rows by expr')

globalCommand('V', 'vd.push(TextSheet("%s[%s].%s" % (name, cursorRowIndex, cursorCol.name), cursorDisplayValue))', 'view readonly contents of this cell in a new sheet')

globalCommand('`', 'vd.push(source if isinstance(source, Sheet) else None)', 'push source sheet')
globalCommand('S', 'vd.push(SheetsSheet("sheets"))', 'open Sheet stack')
globalCommand('C', 'vd.push(ColumnsSheet(sheet.name+"_columns", sheet))', 'open Columns for this sheet')
globalCommand('O', 'vd.push(vd.optionsSheet)', 'open Options for this sheet')
globalCommand('z?', 'vd.push(HelpSheet(name + "_commands", sheet))', 'open command help sheet')
alias('KEY_F(1)', 'z?')


# VisiData uses Python native int, float, str, and adds simple date, currency, and anytype.
#
# A type T is used internally in these ways:
#    o = T(val)   # for interpreting raw value
#    o = T(str)   # for conversion from string (when setting)
#    o = T()      # for default value to be used when conversion fails
#
# The resulting object o must be orderable and convertible to a string for display and certain outputs (like csv).

## minimalist 'any' type
def anytype(r=None):
    return r
anytype.__name__ = ''

option('float_chars', '+-0123456789.eE_', 'valid numeric characters')
def currency(s=''):
    'a `float` with any leading and trailing non-numeric characters stripped'
    floatchars = options.float_chars
    if isinstance(s, str):
        while s and s[0] not in floatchars:
            s = s[1:]
        while s and s[-1] not in floatchars:
            s = s[:-1]
    return float(s) if s else float()

class date:
    '`datetime` wrapper, constructing from time_t or from str with dateutil.parse'

    def __init__(self, s=None):
        if s is None:
            self.dt = datetime.datetime.now()
        elif isinstance(s, int) or isinstance(s, float):
            self.dt = datetime.datetime.fromtimestamp(s)
        elif isinstance(s, str):
            import dateutil.parser
            self.dt = dateutil.parser.parse(s)
        elif isinstance(s, date):
            self.dt = s.dt
        else:
            assert isinstance(s, datetime.datetime), (type(s), s)
            self.dt = s

    def to_string(self, fmtstr=None):
        'Convert datetime object to string, in ISO 8601 format by default.'
        if not fmtstr:
            fmtstr = '%Y-%m-%d %H:%M:%S'
        return self.dt.strftime(fmtstr)

    def __getattr__(self, k):
        'Forward unknown attributes to inner datetime object'
        return getattr(self.dt, k)

    def __str__(self):
        return self.to_string()

    def __lt__(self, a):
        return self.dt < a.dt


typemap = {
    None: 'Ø',
    str: '',
    date: '@',
    int: '#',
    len: '#',
    currency: '$',
    float: '%',
    anytype: '',
}

def joinSheetnames(*sheetnames):
    'Concatenate sheet names in a standard way'
    return '_'.join(str(x) for x in sheetnames)

def error(s):
    'Return custom exception as function, for use with `lambda` and `eval`.'
    raise Exception(s)

def status(*args):
    'Return status property via function call.'
    return vd().status(*args)

def moveListItem(L, fromidx, toidx):
    "Move element within list `L` and return element's new index."
    r = L.pop(fromidx)
    L.insert(toidx, r)
    return toidx

def enumPivot(L, pivotIdx):
    '''Model Python `enumerate()` but starting midway through sequence `L`.

    Begin at index following `pivotIdx`, traverse through end.
    At sequence-end, begin at sequence-head, continuing through `pivotIdx`.'''
    rng = range(pivotIdx+1, len(L))
    rng2 = range(0, pivotIdx+1)
    for i in itertools.chain(rng, rng2):
        yield i, L[i]

def clean_to_id(s):  # [Nas Banov] https://stackoverflow.com/a/3305731
    return re.sub(r'\W|^(?=\d)', '_', str(s))


# VisiData singleton contains all sheets
@functools.lru_cache()
def vd():
    '''Instantiate and return singleton instance of VisiData class.

    Contains all sheets, and (as singleton) is unique instance..'''
    return VisiData()

def exceptionCaught(status=True):
    return vd().exceptionCaught(status)

def stacktrace():
    import traceback
    return traceback.format_exc().strip()

def chooseOne(choices):
    'Return one of `choices` elements (if list) or values (if dict).'
    def choiceCompleter(v, i):
        opts = [x for x in choices if x.startswith(v)]
        return opts[i%len(opts)]

    if isinstance(choices, dict):
        return choices[input('/'.join(choices.keys()) + ': ', completer=choiceCompleter)]
    else:
        return input('/'.join(str(x) for x in choices) + ': ', completer=choiceCompleter)

def regex_flags():
    'Return flags to pass to regex functions from options'
    return sum(getattr(re, f.upper()) for f in options.regex_flags)

def sync(expectedThreads=0):
    'Wait for all async threads to finish.'
    while len(vd().unfinishedThreads) > expectedThreads:
        vd().checkForFinishedThreads()

def async(func):
    'Function decorator, to make calls to `func()` spawn a separate thread if available.'
    def _execAsync(*args, **kwargs):
        return vd().execAsync(func, *args, **kwargs)
    return _execAsync

class VisiData:
    allPrefixes = 'gz'  # 'g'lobal, 'z'scroll

    def __init__(self):
        self.sheets = []
        self.statuses = []  # statuses shown until next action
        self.lastErrors = []
        self.searchContext = {}
        self.statusHistory = []
        self.lastInputs = collections.defaultdict(collections.OrderedDict)  # [input_type] -> prevInputs
        self.keystrokes = ''
        self.inInput = False
        self.scr = None  # curses scr
        self.hooks = {}
        self.threads = []  # all threads, including finished

    def status(self, *args):
        'Add status message to be shown until next action.'
        s = '; '.join(str(x) for x in args)
        self.statuses.append(s)
        self.statusHistory.insert(0, s)
        return s

    def addHook(self, hookname, hookfunc):
        'Add hookfunc by hookname, to be called by corresponding `callHook`.'
        if hookname in self.hooks:
            hooklist = self.hooks[hookname]
        else:
            hooklist = []
            self.hooks[hookname] = hooklist

        hooklist.append(hookfunc)

    def callHook(self, hookname, *args, **kwargs):
        'Call all functions registered with `addHook` for the given hookname.'
        r = None
        for f in self.hooks.get(hookname, []):
            r = r or f(*args, **kwargs)
        return r

    def execAsync(self, func, *args, **kwargs):
        'Execute `func(*args, **kwargs)`, possibly in a separate thread.'
        if threading.current_thread().daemon:
            # Don't spawn a new thread from a subthread.
            return func(*args, **kwargs)

        currentSheet = self.sheets[0]
        thread = threading.Thread(target=self.toplevelTryFunc, daemon=True, args=(func,)+args, kwargs=kwargs)
        self.threads.append(thread)
        currentSheet.currentThreads.append(thread)
        thread.sheet = currentSheet
        thread.start()
        return thread

    def toplevelTryFunc(self, func, *args, **kwargs):
        'Thread entry-point for `func(*args, **kwargs)` with try/except wrapper'
        t = threading.current_thread()
        t.name = func.__name__
        t.startTime = time.process_time()
        t.endTime = None
        t.status = ''
        ret = None
        try:
            ret = func(*args, **kwargs)
        except EscapeException as e:  # user aborted
            t.status += 'aborted by user'
            status('%s aborted' % t.name)
        except Exception as e:
            t.status += status('%s: %s' % (type(e).__name__, ' '.join(str(x) for x in e.args)))
            exceptionCaught()

        t.sheet.currentThreads.remove(t)
        t.sheet.progressMade = t.sheet.progressTotal
        return ret

    @property
    def unfinishedThreads(self):
        'A list of unfinished threads (those without a recorded `endTime`).'
        return [t for t in self.threads if getattr(t, 'endTime') is None]

    def checkForFinishedThreads(self):
        'Mark terminated threads with endTime.'
        for t in self.unfinishedThreads:
            if not t.is_alive():
                t.endTime = time.process_time()
                if not t.status:
                    t.status = 'ended'

    def editText(self, y, x, w, **kwargs):
        'Wrap global editText with `preedit` and `postedit` hooks.'
        v = self.callHook('preedit')
        if v is None:
            cursorEnable(True)
            v = editText(self.scr, y, x, w, **kwargs)
            cursorEnable(False)

        if kwargs.get('display', True):
            self.status('"%s"' % v)
            self.callHook('postedit', v)
        return v

    def getkeystroke(self, scr, vs=None):
        'Get keystroke and display it on status bar.'
        k = None
        try:
            k = scr.get_wch()
            self.drawRightStatus(scr, vs or self.sheets[0]) # continue to display progress %
        except Exception:
            return ''  # curses timeout

        if isinstance(k, str):
            if ord(k) >= 32 and ord(k) != 127:  # 127 == DEL or ^?
                return k
            k = ord(k)
        return curses.keyname(k).decode('utf-8')


    # kwargs: regex=None, columns=None, backward=False
    def searchRegex(self, sheet, moveCursor=False, reverse=False, **kwargs):
        'Set row index if moveCursor, otherwise return list of row indexes.'
        def findMatchingColumn(sheet, row, columns, func):
            'Find column for which func matches the displayed value in this row'
            for c in columns:
                if func(c.getDisplayValue(row)):
                    return c

        self.searchContext.update(kwargs)

        regex = kwargs.get("regex")
        if regex:
            self.searchContext["regex"] = re.compile(regex, regex_flags()) or error('invalid regex: %s' % regex)

        regex = self.searchContext.get("regex") or error("no regex")

        columns = self.searchContext.get("columns")
        if columns == "cursorCol":
            columns = [sheet.cursorCol]
        elif columns == "visibleCols":
            columns = tuple(sheet.visibleCols)
        elif isinstance(columns, Column):
            columns = [columns]

        if not columns:
            error('bad columns')

        searchBackward = self.searchContext.get("backward")
        if reverse:
            searchBackward = not searchBackward

        if searchBackward:
            rng = range(sheet.cursorRowIndex-1, -1, -1)
            rng2 = range(sheet.nRows-1, sheet.cursorRowIndex-1, -1)
        else:
            rng = range(sheet.cursorRowIndex+1, sheet.nRows)
            rng2 = range(0, sheet.cursorRowIndex+1)

        matchingRowIndexes = 0
        sheet.progressTotal = sheet.nRows
        sheet.progressMade = 0

        for r in itertools.chain(rng, rng2):
            sheet.progressMade += 1
            c = findMatchingColumn(sheet, sheet.rows[r], columns, regex.search)
            if c:
                if moveCursor:
                    sheet.cursorRowIndex = r
                    sheet.cursorVisibleColIndex = sheet.visibleCols.index(c)
                    if r in rng2:
                        status('search wrapped')
                    return
                else:
                    matchingRowIndexes += 1
                    yield r

        status('%s matches for /%s/' % (matchingRowIndexes, regex.pattern))

    def exceptionCaught(self, status=True):
        'Maintain list of most recent errors and return most recent one.'
        self.lastErrors.append(stacktrace())
        self.lastErrors = self.lastErrors[-10:]  # keep most recent
        if status:
            return self.status(self.lastErrors[-1].splitlines()[-1])
        if options.debug:
            raise

    def drawLeftStatus(self, scr, vs):
        'Draw left side of status bar.'
        try:
            lstatus = self.leftStatus(vs)
            attr = colors[options.color_status]
            _clipdraw(scr, self.windowHeight-1, 0, lstatus, attr, self.windowWidth)
        except Exception as e:
            self.exceptionCaught()

    def drawRightStatus(self, scr, vs):
        'Draw right side of status bar.'
        try:
            rstatus, attr = self.rightStatus(vs)
            _clipdraw(scr, self.windowHeight-1, self.windowWidth-len(rstatus)-2, rstatus, attr, len(rstatus))
            curses.doupdate()
        except Exception as e:
            self.exceptionCaught()

    def leftStatus(self, vs):
        'Compose left side of status bar and add status messages.'
        s = vs.leftStatus()
        s += options.disp_status_sep.join(self.statuses)
        return s

    def rightStatus(self, sheet):
        'Compose right side of status bar.'
        if sheet.progressMade == sheet.progressTotal:
            pctLoaded = 'rows'
        else:
            pctLoaded = ' %2d%%' % sheet.progressPct
        status = '%s %9d %s' % (self.keystrokes, sheet.nRows, pctLoaded)
        attr = colors[options.color_status]
        return status, attr

    @property
    def windowHeight(self):
        return self.scr.getmaxyx()[0] if self.scr else 25

    @property
    def windowWidth(self):
        return self.scr.getmaxyx()[1] if self.scr else 80

    def run(self, scr):
        'Manage execution of keystrokes and subsequent redrawing of screen.'
        global sheet
        scr.timeout(int(options.curses_timeout))
        cursorEnable(False)

        self.scr = scr

        self.keystrokes = ''
        while True:
            if not self.sheets:
                # if no more sheets, exit
                return

            sheet = self.sheets[0]

            try:
                sheet.draw(scr)
            except Exception as e:
                self.exceptionCaught()

            self.drawLeftStatus(scr, sheet)
            self.drawRightStatus(scr, sheet)  # visible during this getkeystroke

            keystroke = self.getkeystroke(scr, sheet)
            if keystroke:
                if self.keystrokes not in self.allPrefixes:
                    self.keystrokes = ''

                self.statuses = []
                self.keystrokes += keystroke

            self.drawRightStatus(scr, sheet)  # visible for commands that wait for input

            if not keystroke:  # timeout instead of keypress
                pass
            elif keystroke == '^Q':
                return self.lastErrors and self.lastErrors[-1]
            elif keystroke == 'KEY_RESIZE':
                pass
            elif keystroke == 'KEY_MOUSE':
                try:
                    devid, x, y, z, bstate = curses.getmouse()
                    sheet.cursorRowIndex = sheet.topRowIndex+y-1
                except curses.error:
                    pass
            elif self.keystrokes in sheet._commands:
                sheet.exec_keystrokes(self.keystrokes)
            elif keystroke in self.allPrefixes:
                pass
            else:
                status('no command for "%s"' % (self.keystrokes))

            self.checkForFinishedThreads()
            self.callHook('predraw')
            sheet.checkCursor()

    def replace(self, vs):
        'Replace top sheet with the given sheet `vs`.'
        self.sheets.pop(0)
        return self.push(vs)

    def remove(self, vs):
        if vs in self.sheets:
            self.sheets.remove(vs)
        else:
            error('sheet not on stack')

    def push(self, vs):
        'Move given sheet `vs` to index 0 of list `sheets`.'
        if vs:
            vs.vd = self
            if vs in self.sheets:
                self.sheets.remove(vs)
                self.sheets.insert(0, vs)
            elif len(vs.rows) == 0:  # first time
                self.sheets.insert(0, vs)
                vs.reload()
                vs.recalc()  # set up Columns
            else:
                self.sheets.insert(0, vs)
            return vs
# end VisiData class

class LazyMap:
    'provides a lazy mapping to obj attributes.  useful when some attributes are expensive properties.'
    def __init__(self, obj):
        self.obj = obj

    def keys(self):
        return dir(self.obj)

    def __getitem__(self, k):
        if k not in dir(self.obj):
            raise KeyError(k)
        return getattr(self.obj, k)

    def __setitem__(self, k, v):
        setattr(self.obj, k, v)

class Colorizer:
    def __init__(self, colorizerType, precedence, colorfunc):
        self.type = colorizerType
        self.precedence = precedence
        self.func = colorfunc

class Sheet:
    columns = []  # list of Column
    commands = []  # list of (keystrokes, helpstr, execstr)
    colorizers = [ # list of Colorizer
        Colorizer('hdr', 0, lambda s,c,r,v: options.color_default_hdr),
        Colorizer('hdr', 9, lambda s,c,r,v: options.color_current_hdr if c is s.cursorCol else None),
        Colorizer('hdr', 8, lambda s,c,r,v: options.color_key_col if c in s.keyCols else None),
        Colorizer('col', 5, lambda s,c,r,v: options.color_current_col if c is s.cursorCol else None),
        Colorizer('col', 7, lambda s,c,r,v: options.color_key_col if c in s.keyCols else None),
        Colorizer('cell', 2, lambda s,c,r,v: options.color_default),
        Colorizer('row', 8, lambda s,c,r,v: options.color_selected_row if s.isSelected(r) else None),
    ]
    nKeys = 0  # self.columns[:nKeys] are all pinned to the left and matched on join

    def __init__(self, name, *sources, **kwargs):
        self.name = name
        self.sources = list(sources)

        self.rows = []           # list of opaque row objects
        self.cursorRowIndex = 0  # absolute index of cursor into self.rows
        self.cursorVisibleColIndex = 0  # index of cursor into self.visibleCols

        self.topRowIndex = 0     # cursorRowIndex of topmost row
        self.leftVisibleColIndex = 0    # cursorVisibleColIndex of leftmost column
        self.rightVisibleColIndex = 0
        self.loader = None

        # as computed during draw()
        self.rowLayout = {}      # [rowidx] -> y
        self.visibleColLayout = {}      # [vcolidx] -> (x, w)

        # all columns in display order
        self.columns = kwargs.get('columns') or [copy(c) for c in self.columns]  # list of Column objects

        # commands specific to this sheet
        sheetcmds = collections.OrderedDict()
        for ks, helpstr, execstr in self.commands:
            _registerCommand(sheetcmds, ks, execstr, helpstr)
        self._commands = collections.ChainMap(sheetcmds, baseCommands)

        self._selectedRows = {}  # id(row) -> row

        # for progress bar
        self.progressMade = 0
        self.progressTotal = 0

        # track all async tasks from sheet
        self.currentThreads = []

        self._colorizers = {'row': [], 'col': [], 'hdr': [], 'cell': []}

        for b in [self] + list(self.__class__.__bases__):
            for c in getattr(b, 'colorizers', []):
                self._colorizers[c.type].append(c)

        self.__dict__.update(kwargs)

    def colorizeRow(self, row):
        return self.colorize(['row'], None, row)

    def colorizeColumn(self, col):
        return self.colorize(['col'], col, None)

    def colorizeHdr(self, col):
        return self.colorize(['hdr'], col, None)

    def colorizeCell(self, col, row, value):
        return self.colorize(['col', 'row', 'cell'], col, row, value)

    def colorize(self, colorizerTypes, col, row, value=None):
        'Returns curses attribute for the given col/row/value'
        attr = 0
        attrpre = 0

        for colorizerType in colorizerTypes:
            for colorizer in sorted(self._colorizers[colorizerType], key=lambda x: x.precedence):
                color = colorizer.func(self, col, row, value)
                if color:
                    attr, attrpre = colors.update(attr, attrpre, color, colorizer.precedence)

        return attr

    def leftStatus(self):
        'Compose left side of status bar for this sheet (overridable).'
        return options.disp_status_fmt.format(sheet=self)

    def genProgress(self, L, total=None):
        self.progressTotal = total or len(L)
        self.progressMade = 0
        for i in L:
            self.progressMade += 1
            yield i

        self.progressMade = self.progressTotal

    def addRow(self, row, index=None):
        if index is None:
            self.rows.append(row)
        else:
            self.rows.insert(index, row)

    def moveRegex(self, *args, **kwargs):
        'Wrap `VisiData.searchRegex`, with cursor additionally moved.'
        list(self.searchRegex(*args, moveCursor=True, **kwargs))

    def searchRegex(self, *args, **kwargs):
        'Wrap `VisiData.searchRegex`.'
        return self.vd.searchRegex(self, *args, **kwargs)

    def searchColumnNameRegex(self, colregex, moveCursor=False):
        'Select visible column matching `colregex`, if found.'
        for i, c in enumPivot(self.visibleCols, self.cursorVisibleColIndex):
            if re.search(colregex, c.name, regex_flags()):
                if moveCursor:
                    self.cursorVisibleColIndex = i
                return c

    def recalc(self):
        for c in self.columns:
            if c._cachedValues:
                c._cachedValues.clear()
            c.sheet = self

    def reload(self):
        'Default reloader wraps provided `loader` function'
        if self.loader:
            self.loader()
        else:
            status('no reloader')

    def __copy__(self):
        'copy sheet design (no rows).  deepcopy columns so their attributes (width, type, name) may be adjusted independently.'
        cls = self.__class__
        ret = cls.__new__(cls)
        ret.__dict__.update(self.__dict__)
        ret.sources = copy(self.sources)  # same sources in a fresh list
        ret.rows = []                     # a fresh list without incurring any overhead
#        ret.rows = copy(self.rows)       # same row objects in a fresh list
        ret.columns = deepcopy(self.columns) # deepcopy columns even for shallow copy of sheet
        for c in ret.columns:
            c.sheet = ret
        ret._selectedRows = {}
        ret.topRowIndex = ret.cursorRowIndex = 0
        ret.progressMade = ret.progressTotal = 0
        ret.currentThreads = []
        return ret

    def __deepcopy__(self, memo):
        'same as Sheet.__copy__'
        ret = self.__copy__()
        memo[id(self)] = ret
        return ret

    @async
    def deleteSelected(self):
        'Delete all selected rows.'
        oldrows = copy(self.rows)
        oldidx = self.cursorRowIndex
        ndeleted = 0

        row = None   # row to re-place cursor after
        while oldidx < len(oldrows):
            if not self.isSelected(oldrows[oldidx]):
                row = self.rows[oldidx]
                break
            oldidx += 1

        self.rows.clear()
        for r in self.genProgress(oldrows):
            if not self.isSelected(r):
                self.rows.append(r)
                if r is row:
                    self.cursorRowIndex = len(self.rows)-1
            else:
                ndeleted += 1

        nselected = len(self._selectedRows)
        self._selectedRows.clear()
        status('deleted %s rows' % ndeleted)
        if ndeleted != nselected:
            error('expected %s' % nselected)

    def __repr__(self):
        return self.name

    def evalexpr(self, expr, row):
        return eval(expr, getGlobals(), LazyMapping(self, row))

    def exec_keystrokes(self, keystrokes, vdglobals=None):  # handle multiple commands concatenated?
        return self.exec_command(self._commands[keystrokes], vdglobals)

    def exec_command(self, cmd, vdglobals=None):
        "Execute `cmd` tuple with `vdglobals` as globals and this sheet's attributes as locals.  Returns True if user cancelled."
        escaped = False
        err = ''

        if vdglobals is None:
            vdglobals = globals()

        keystrokes, _, execstr = cmd
        self.sheet = self

        try:
            self.vd.callHook('preexec', self, keystrokes)
            exec(execstr, vdglobals, LazyMap(self))
        except EscapeException as e:  # user aborted
            self.vd.status(e.args[0])
            escaped = True
        except Exception:
            err = self.vd.exceptionCaught()

        try:
            self.vd.callHook('postexec', self.vd.sheets[0] if self.vd.sheets else None, escaped, err)
        except Exception:
            self.vd.exceptionCaught()

        return escaped

    @property
    def name(self):
        return self._name

    @name.setter
    def name(self, name):
        'Set name without spaces.'
        self._name = name.replace(' ', '_')

    @property
    def source(self):
        'Return first source, if any.'
        if not self.sources:
            return None
        else:
#            assert len(self.sources) == 1, len(self.sources)
            return self.sources[0]

    @property
    def progressPct(self):
        'Percent complete as indicated by async actions.'
        if self.progressTotal != 0:
            return int(self.progressMade*100/self.progressTotal)
        return 0

    @property
    def nVisibleRows(self):
        'Number of visible rows at the current window height.'
        return self.vd.windowHeight-2

    @property
    def cursorCol(self):
        'Current Column object.'
        return self.visibleCols[self.cursorVisibleColIndex]

    @property
    def cursorRow(self):
        'The row object at the row cursor.'
        return self.rows[self.cursorRowIndex]

    @property
    def visibleRows(self):  # onscreen rows
        'Slice of rows visible in the window.'
        return self.rows[self.topRowIndex:self.topRowIndex+self.nVisibleRows]

    @property
    def visibleCols(self):  # non-hidden cols
        'List of unhidden Column objects.'
        return [c for c in self.columns if not c.hidden]

    @property
    def visibleColNames(self):
        'String of visible column names.'
        return ' '.join(c.name for c in self.visibleCols)

    @property
    def cursorColIndex(self):
        'Index of column into cursor.columns.'
        return self.columns.index(self.cursorCol)

    @property
    def keyCols(self):
        'List of key columns.'
        return self.columns[:self.nKeys]

    @property
    def nonKeyVisibleCols(self):
        'List of unhidden non-key columns.'
        return [c for c in self.columns[self.nKeys:] if not c.hidden]

    @property
    def keyColNames(self):
        'String of key column names.'
        return options.disp_key_sep.join(c.name for c in self.keyCols)

    @property
    def cursorCell(self):
        'Displayed value (DisplayWrapper) at current row and column.'
        return self.cursorCol.getCell(self.cursorRow)

    @property
    def cursorDisplay(self):
        'Displayed value (DisplayWrapper.display) at current row and column.'
        return self.cursorCol.getDisplayValue(self.cursorRow)

    @property
    def cursorTypedValue(self):
        'Typed value at current row and column.'
        return self.cursorCol.getTypedValue(self.cursorRow)

    @property
    def cursorValue(self):
        'Untyped value at current row and column.'
        return self.cursorCol.getValue(self.cursorRow)

    @property
    def statusLine(self):
        'Status-line element showing row and column stats.'
        rowinfo = 'row %d/%d (%d selected)' % (self.cursorRowIndex, self.nRows, len(self._selectedRows))
        colinfo = 'col %d/%d (%d visible)' % (self.cursorColIndex, self.nCols, len(self.visibleCols))
        return '%s  %s' % (rowinfo, colinfo)

    @property
    def nRows(self):
        'Number of rows on this sheet.'
        return len(self.rows)

    @property
    def nCols(self):
        'Number of columns on this sheet.'
        return len(self.columns)

    @property
    def nVisibleCols(self):
        'Number of visible columns on this sheet.'
        return len(self.visibleCols)

## selection code
    def isSelected(self, r):
        'Return boolean: is current row selected?'
        return id(r) in self._selectedRows

    @async
    def toggle(self, rows):
        'Select any unselected rows.'
        for r in self.genProgress(rows, len(self.rows)):
            if not self.unselectRow(r):
                self.selectRow(r)

    def selectRow(self, row):
        'Select given row.'
        self._selectedRows[id(row)] = row

    def unselectRow(self, row):
        'Unselect given row, return True if selected; else return False.'
        if id(row) in self._selectedRows:
            del self._selectedRows[id(row)]
            return True
        else:
            return False

    @async
    def select(self, rows, status=True, progress=True):
        'Select given rows with option for progress-tracking.'
        before = len(self._selectedRows)
        for r in (self.genProgress(rows) if progress else rows):
            self.selectRow(r)
        if status:
            self.vd.status('selected %s%s rows' % (len(self._selectedRows)-before, ' more' if before > 0 else ''))

    @async
    def unselect(self, rows, status=True, progress=True):
        'Unselect given rows with option for progress-tracking.'
        before = len(self._selectedRows)
        for r in (self.genProgress(rows) if progress else rows):
            self.unselectRow(r)
        if status:
            self.vd.status('unselected %s/%s rows' % (before-len(self._selectedRows), before))

    def selectByIdx(self, rowIdxs):
        'Select given rows by index numbers.'
        self.select((self.rows[i] for i in rowIdxs), progress=False)

    def unselectByIdx(self, rowIdxs):
        'Unselect given rows by index numbers.'
        self.unselect((self.rows[i] for i in rowIdxs), progress=False)

    def gatherBy(self, func):
        'Yield each row matching the cursor value '
        for r in self.genProgress(self.rows):
            if func(r):
                yield r

    @property
    def selectedRows(self):
        'Return a list of selected rows in sheet order.'
        return [r for r in self.rows if id(r) in self._selectedRows]

## end selection code

    def moveVisibleCol(self, fromVisColIdx, toVisColIdx):
        'Move column to another position in sheet.'
        fromColIdx = self.columns.index(self.visibleCols[fromVisColIdx])
        toColIdx = self.columns.index(self.visibleCols[toVisColIdx])
        moveListItem(self.columns, fromColIdx, toColIdx)
        return toVisColIdx

    def cursorDown(self, n=1):
        "Increment cursor's row by `n`."
        self.cursorRowIndex += n

    def cursorRight(self, n=1):
        "Increment cursor's column by `n`."
        self.cursorVisibleColIndex += n
        self.calcColLayout()

    def pageLeft(self):
        '''Redraw page one screen to the left.

        Note: keep the column cursor in the same general relative position:

         - if it is on the furthest right column, then it should stay on the
           furthest right column if possible

         - likewise on the left or in the middle

        So really both the `leftIndex` and the `cursorIndex` should move in
        tandem until things are correct.'''

        targetIdx = self.leftVisibleColIndex  # for rightmost column
        firstNonKeyVisibleColIndex = self.visibleCols.index(self.nonKeyVisibleCols[0])
        while self.rightVisibleColIndex != targetIdx and self.leftVisibleColIndex > firstNonKeyVisibleColIndex:
            self.cursorVisibleColIndex -= 1
            self.leftVisibleColIndex -= 1
            self.calcColLayout()  # recompute rightVisibleColIndex

        # in case that rightmost column is last column, try to squeeze maximum real estate from screen
        if self.rightVisibleColIndex == self.nVisibleCols-1:
            # try to move further left while right column is still full width
            while self.leftVisibleColIndex > 0:
                rightcol = self.visibleCols[self.rightVisibleColIndex]
                if rightcol.width > self.visibleColLayout[self.rightVisibleColIndex][1]:
                    # went too far
                    self.cursorVisibleColIndex += 1
                    self.leftVisibleColIndex += 1
                    break
                else:
                    self.cursorVisibleColIndex -= 1
                    self.leftVisibleColIndex -= 1
                    self.calcColLayout()  # recompute rightVisibleColIndex

    def addColumn(self, col, index=None):
        'Insert column at given index or after all columns.'
        if col:
            if index is None:
                index = len(self.columns)
            col.sheet = self
            self.columns.insert(index, col)

    def toggleKeyColumn(self, colidx):
        'Toggle column at given index as key column.'
        if colidx >= self.nKeys: # if not a key, add it
            moveListItem(self.columns, colidx, self.nKeys)
            self.nKeys += 1
            return 1
        else:  # otherwise move it after the last key
            self.nKeys -= 1
            moveListItem(self.columns, colidx, self.nKeys)
            return 0

    def moveToNextRow(self, func, reverse=False):
        'Move cursor to next (prev if reverse) row for which func returns True.  Returns False if no row meets the criteria.'
        rng = range(self.cursorRowIndex-1, -1, -1) if reverse else range(self.cursorRowIndex+1, self.nRows)

        for i in rng:
            if func(self.rows[i]):
                self.cursorRowIndex = i
                return True

        return False

    def checkCursor(self):
        'Keep cursor in bounds of data and screen.'
        # keep cursor within actual available rowset
        if self.nRows == 0 or self.cursorRowIndex <= 0:
            self.cursorRowIndex = 0
        elif self.cursorRowIndex >= self.nRows:
            self.cursorRowIndex = self.nRows-1

        if self.cursorVisibleColIndex <= 0:
            self.cursorVisibleColIndex = 0
        elif self.cursorVisibleColIndex >= self.nVisibleCols:
            self.cursorVisibleColIndex = self.nVisibleCols-1

        if self.topRowIndex <= 0:
            self.topRowIndex = 0
        elif self.topRowIndex > self.nRows-self.nVisibleRows:
            self.topRowIndex = self.nRows-self.nVisibleRows

        # (x,y) is relative cell within screen viewport
        x = self.cursorVisibleColIndex - self.leftVisibleColIndex
        y = self.cursorRowIndex - self.topRowIndex + 1  # header

        # check bounds, scroll if necessary
        if y < 1:
            self.topRowIndex = self.cursorRowIndex
        elif y > self.nVisibleRows:
            self.topRowIndex = self.cursorRowIndex-self.nVisibleRows+1

        if x <= 0:
            self.leftVisibleColIndex = self.cursorVisibleColIndex
        else:
            while True:
                if self.leftVisibleColIndex == self.cursorVisibleColIndex:  # not much more we can do
                    break
                self.calcColLayout()
                if self.cursorVisibleColIndex < min(self.visibleColLayout.keys()):
                    self.leftVisibleColIndex -= 1
                    continue
                elif self.cursorVisibleColIndex > max(self.visibleColLayout.keys()):
                    self.leftVisibleColIndex += 1
                    continue

                cur_x, cur_w = self.visibleColLayout[self.cursorVisibleColIndex]
                if cur_x+cur_w < self.vd.windowWidth:  # current columns fit entirely on screen
                    break
                self.leftVisibleColIndex += 1

    def calcColLayout(self):
        'Set right-most visible column, based on calculation.'
        self.visibleColLayout = {}
        x = 0
        vcolidx = 0
        for vcolidx in range(0, self.nVisibleCols):
            col = self.visibleCols[vcolidx]
            if col.width is None and self.visibleRows:
                col.width = col.getMaxWidth(self.visibleRows)+len(options.disp_more_left)+len(options.disp_more_right)
            width = col.width if col.width is not None else col.getMaxWidth(self.visibleRows)  # handle delayed column width-finding
            if col in self.keyCols or vcolidx >= self.leftVisibleColIndex:  # visible columns
                self.visibleColLayout[vcolidx] = [x, min(width, self.vd.windowWidth-x)]
                x += width+len(options.disp_column_sep)
            if x > self.vd.windowWidth-1:
                break

        self.rightVisibleColIndex = vcolidx

    def drawColHeader(self, scr, y, vcolidx):
        'Compose and draw column header for given vcolidx.'
        col = self.visibleCols[vcolidx]

        # hdrattr highlights whole column header
        # sepattr is for header separators and indicators
        sepattr = colors[options.color_column_sep]
        hdrattr = self.colorizeHdr(col)

        C = options.disp_column_sep
        if (self.keyCols and col is self.keyCols[-1]) or vcolidx == self.rightVisibleColIndex:
            C = options.disp_keycol_sep

        x, colwidth = self.visibleColLayout[vcolidx]

        # ANameTC
        T = typemap.get(col.type, '?')
        N = ' ' + (col.name or defaultColNames[vcolidx])  # save room at front for LeftMore
        if len(N) > colwidth-1:
            N = N[:colwidth-len(options.disp_truncator)] + options.disp_truncator
        _clipdraw(scr, y, x, N, hdrattr, colwidth)
        _clipdraw(scr, y, x+colwidth-len(T), T, hdrattr, len(T))

        if vcolidx == self.leftVisibleColIndex and col not in self.keyCols and self.nonKeyVisibleCols.index(col) > 0:
            A = options.disp_more_left
            scr.addstr(y, x, A, sepattr)

        if C and x+colwidth+len(C) < self.vd.windowWidth:
            scr.addstr(y, x+colwidth, C, sepattr)

    def isVisibleIdxKey(self, vcolidx):
        'Return boolean: is given column index a key column?'
        return self.visibleCols[vcolidx] in self.keyCols

    def draw(self, scr):
        'Draw entire screen onto the `scr` curses object.'
        numHeaderRows = 1
        scr.erase()  # clear screen before every re-draw

        if not self.columns:
            return

        self.rowLayout = {}
        self.calcColLayout()
        for vcolidx, colinfo in sorted(self.visibleColLayout.items()):
            x, colwidth = colinfo
            col = self.visibleCols[vcolidx]

            if x < self.vd.windowWidth:  # only draw inside window
                headerRow = 0
                self.drawColHeader(scr, headerRow, vcolidx)

                y = headerRow + numHeaderRows

                for rowidx in range(0, self.nVisibleRows):
                    dispRowIdx = self.topRowIndex + rowidx
                    if dispRowIdx >= self.nRows:
                        break

                    self.rowLayout[dispRowIdx] = y

                    row = self.rows[dispRowIdx]
                    cellval = col.getCell(row, colwidth-1)

                    attr = self.colorizeCell(col, row, cellval)
                    attrpre = 0
                    sepattr = self.colorizeRow(row)

                    # must apply current row here, because this colorization requires cursorRowIndex
                    if dispRowIdx == self.cursorRowIndex:
                        attr, attrpre = colors.update(attr, 0, options.color_current_row, 10)
                        sepattr, _ = colors.update(sepattr, 0, options.color_current_row, 10)

                    sepattr = sepattr or colors[options.color_column_sep]

                    _clipdraw(scr, y, x, options.disp_column_fill+cellval.display, attr, colwidth)

                    note = getattr(cellval, 'note', None)

                    if note:
                        noteattr, _ = colors.update(attr, attrpre, cellval.notecolor, 8)
                        _clipdraw(scr, y, x+colwidth-len(note), note, noteattr, len(note))

                    sepchars = options.disp_column_sep
                    if (self.keyCols and col is self.keyCols[-1]) or vcolidx == self.rightVisibleColIndex:
                        sepchars = options.disp_keycol_sep

                    if x+colwidth+len(sepchars) <= self.vd.windowWidth:
                       scr.addstr(y, x+colwidth, sepchars, sepattr)

                    y += 1

        if vcolidx+1 < self.nVisibleCols:
            scr.addstr(headerRow, self.vd.windowWidth-2, options.disp_more_right, colors[options.color_column_sep])


    def editCell(self, vcolidx=None, rowidx=None):
        'Call `editText` at its place on the screen.  Returns the new value, properly typed'

        if options.readonly:
            status('readonly mode')
            return
        if vcolidx is None:
            vcolidx = self.cursorVisibleColIndex
        x, w = self.visibleColLayout.get(vcolidx, (0, 0))

        col = self.visibleCols[vcolidx]
        if rowidx is None:
            rowidx = self.cursorRowIndex
        if rowidx < 0:  # header
            y = 0
            currentValue = col.name
        else:
            y = self.rowLayout.get(rowidx, 0)
            currentValue = col.getValue(self.rows[self.cursorRowIndex])

        r = self.vd.editText(y, x, w, value=currentValue, fillchar=options.disp_edit_fill, truncchar=options.disp_truncator)
        if rowidx >= 0:
            r = col.type(r)  # convert input to column type

        return r

def isNullFunc():
    return {
                'n': lambda v: v is None,
                'e': lambda v: v is None or v == '',
                'f': lambda v: not bool(v)
           }.get(options.aggr_null_filter[:1].lower(), lambda v: False)

class Column:
    def __init__(self, name, type=anytype, cache=False, **kwargs):
        self.sheet = None     # owning sheet, set in Sheet.addColumn
        self._id = None       # identifier for this column, usable in expressions
        self.name = name      # display visible name; uses setter from the get-go to fill in _id also
        self.fmtstr = ''      # by default, use str()
        self.type = type      # anytype/str/int/float/date/func
        self.getter = lambda row: row
        self.full_getter = lambda sheet,col,row: col.getter(row)
        self.setter = None    # setter(sheet,col,row,value)
        self.width = None     # == 0 if hidden, None if auto-compute next time

        self._cachedValues = collections.OrderedDict() if cache else None
        for k, v in kwargs.items():
            setattr(self, k, v)  # instead of __dict__.update(kwargs) to invoke property.setters

    def __copy__(self):
        cls = self.__class__
        ret = cls.__new__(cls)
        ret.__dict__.update(self.__dict__)
        if ret._cachedValues:
            ret._cachedValues = collections.OrderedDict()  # a fresh cache
        return ret

    def __deepcopy__(self, memo):
        return self.__copy__()  # no separate deepcopy

    @property
    def name(self):
        return self._name or self._id or ''

    @name.setter
    def name(self, name):
        name = name.strip()
        if options.force_valid_colnames:
            name = clean_to_id(name)
        self._name = name
        self._id = name or self.sheet and defaultColNames[self.sheet.columns.index(self)]

    @property
    def fmtstr(self):
        if self._fmtstr:
            return self._fmtstr

        t = self.type
        if t is int:      return '{:d}'
        elif t is float:    return '{:.02f}'
        elif t is currency: return '{:,.02f}'

    @fmtstr.setter
    def fmtstr(self, v):
        self._fmtstr = v

    def format(self, cellval):
        'Return displayable string of `cellval` according to our `Column.type` and `Column.fmtstr`'
        if cellval is None:
            return options.disp_none

        if isinstance(cellval, (list, dict)):
            # complex objects can be arbitrarily large (like sheet.rows)
            return str(type(cellval))

        t = self.type
        typedval = t(cellval)
        if t is date:         return typedval.to_string(self.fmtstr)
        elif self.fmtstr:     return self.fmtstr.format(typedval)
        else:                 return str(typedval)

    @property
    def hidden(self):
        'A column is hidden if its width == 0.'
        return self.width == 0

    def getValueRows(self, rows):
        'Generate (val, row) for the given `rows` at this Column, excluding errors and nulls.'
        f = isNullFunc()

        for r in rows:
            try:
                v = self.type(self.getValue(r))
                if not f(v):
                    yield v, r
            except:
                pass

    def getValues(self, rows):
        for v, r in self.getValueRows(rows):
            yield v

    def calcValue(self, row):
        return self.full_getter(self.sheet, self, row)

    def getTypedValue(self, row):
        '''Returns the properly-typed value for the given row at this column.
           Returns the type's default value if either the getter or the type conversion fails.'''
        try:
            return self.type(self.getValue(row))
        except EscapeException:
            raise
        except Exception as e:
            exceptionCaught(status=False)
            return self.type()

    def getValue(self, row):
        'Memoize calcValue with key id(row)'
        if self._cachedValues is None:
            return self.calcValue(row)

        k = id(row)
        if k in self._cachedValues:
            return self._cachedValues[k]

        ret = self.calcValue(row)
        self._cachedValues[k] = ret

        if len(self._cachedValues) > 256:  # max number of entries
            self._cachedValues.popitem(last=False)

        return ret

    def getCell(self, row, width=None):
        'Return DisplayWrapper for displayable cell value.'
        try:
            cellval = self.getValue(row)
        except EscapeException:
            raise
        except Exception as e:
#            exceptionCaught(status=False)
            return DisplayWrapper(None, error=stacktrace(),
                                display=options.disp_error_val,
                                note=options.disp_getter_exc,
                                notecolor=options.color_getter_exc)

        if isinstance(cellval, bytes):
            cellval = cellval.decode(options.encoding, options.encoding_errors)

        try:
            dispval = self.format(cellval)
            if width and self.type in (int, float, currency):
                dispval = dispval.rjust(width-1)

            # annotate cells with raw value type in anytype columns
            if self.type is anytype and options.color_type_note:
                return DisplayWrapper(cellval, display=dispval,
                        note=typemap.get(type(cellval), None),
                        notecolor=options.color_type_note)

            return DisplayWrapper(cellval, display=dispval)
        except EscapeException:
            raise
        except Exception as e:  # type conversion or formatting failed
#            exceptionCaught(status=False)
            return DisplayWrapper(cellval, error=stacktrace(),
                                display=str(cellval),
                                note=options.disp_format_exc,
                                notecolor=options.color_format_exc)

    def getDisplayValue(self, row):
        return self.getCell(row).display

    def setValue(self, row, value):
        if not self.setter:
            error('column cannot be changed')
        self.setter(self.sheet, self, row, value)

    def setValues(self, rows, value):
        'Set given rows to `value`.'
        value = self.type(value)
        for r in rows:
            self.setValue(r, value)
        status('set %d values = %s' % (len(rows), value))

    @async
    def setValuesFromExpr(self, rows, expr):
        compiledExpr = compile(expr, '<expr>', 'eval')
        for row in self.sheet.genProgress(rows):
            self.setValue(row, self.sheet.evalexpr(compiledExpr, row))
        status('set %d values = %s' % (len(rows), expr))

    def getMaxWidth(self, rows):
        'Return the maximum length of any cell in column or its header.'
        w = 0
        if len(rows) > 0:
            w = max(max(len(self.getDisplayValue(r)) for r in rows), len(self.name))+2
        return max(w, len(self.name))

    def toggleWidth(self, width):
        'Change column width to either given `width` or default value.'
        if self.width != width:
            self.width = width
        else:
            self.width = int(options.default_width)


# ---- Column makers

def setitem(r, i, v):  # function needed for use in lambda
    r[i] = v

def ColumnAttr(name, attr=None, **kwargs):
    'Return Column object with `attrname` from current row Python object.'
    if attr is None:
        attr = name
    return Column(name,
            getter=lambda r,b=attr: getattr(r,b,None),
            setter=lambda s,c,r,v,b=attr: setattr(r,b,v),
            **kwargs)

def ColumnItem(name, key=None, **kwargs):
    'Return Column object (with getitem/setitem) on the row Python object.'
    if key is None:
        key = name
    return Column(name,
            getter=lambda r,i=key: r[i],
            setter=lambda s,c,r,v,i=key,f=setitem: f(r,i,v),
            **kwargs)

def ArrayNamedColumns(columns):
    '''Return list of Column objects from named columns.

    Note: argument `columns` is a list of column names, Mapping to r[0]..r[n].'''
    return [ColumnItem(colname, i) for i, colname in enumerate(columns)]

def ArrayColumns(ncols):
    'Return list of Columns that __getitem__ on the row'
    return [ColumnItem('', i, width=8) for i in range(ncols)]


class SubrowColumn(Column):
    def __init__(self, origcol, subrowidx, **kwargs):
        super().__init__(origcol.name, type=origcol.type, width=origcol.width, **kwargs)
        self.origcol = origcol
        self.subrowidx = subrowidx

    def getValue(self, row):
        subrow = row[self.subrowidx]
        return subrow and self.origcol.getValue(subrow) or None

    def setValue(self, row, value):
        subrow = row[self.subrowidx]
        return subrow and self.origcol.setValue(subrow, value) or None


class DisplayWrapper:
    def __init__(self, value, **kwargs):
        self.value = value
        self.__dict__.update(kwargs)

    def is_error(self):
        return False

    def is_null(self):
        return self.value is None or self.value is ''


class ColumnEnum(Column):
    'types and aggregators. row.<name> should be kept to the values in the mapping m, and can be set by the a string key into the mapping.'
    def __init__(self, name, m, default=None):
        super().__init__(name)
        self.mapping = m
        self.default = default

    def getValue(self, row):
        v = getattr(row, self.name, None)
        return v.__name__ if v else None

    def setValue(self, row, value):
        if isinstance(value, str):  # first try to get the actual value from the mapping
            value = self.mapping.get(value, value)
        setattr(row, self.name, value or self.default)


class LazyMapping:
    'Calculate column values as needed.'
    def __init__(self, sheet, row):
        self.row = row
        self.sheet = sheet

    def keys(self):
        return [c._id for c in self.sheet.columns]

    def __getitem__(self, colid):
        colids = self.keys()
        if colid in colids:
            i = colids.index(colid)
            return self.sheet.columns[i].getTypedValue(self.row)
        else:
            raise KeyError(colid)

#    def __getattr__(self, colid):
#        return self.__getitem__(colid)


class ColumnExpr(Column):
    def __init__(self, expr):
        super().__init__(expr)
        self.compiledExpr = compile(expr, '<expr>', 'eval')

    def calcValue(self, row):
        return self.sheet.evalexpr(self.compiledExpr, row)

###

def input(prompt, type='', **kwargs):
    'Compose input prompt.'
    if type:
        ret = _inputLine(prompt, history=list(vd().lastInputs[type].keys()), **kwargs)
        vd().lastInputs[type][ret] = ret
    else:
        ret = _inputLine(prompt, **kwargs)
    return ret

def _inputLine(prompt, **kwargs):
    'Add prompt to bottom of screen and get line of input from user.'
    scr = vd().scr
    if scr:
        scr.addstr(vd().windowHeight-1, 0, prompt)
    vd().inInput = True
    ret = vd().editText(vd().windowHeight-1, len(prompt), vd().windowWidth-len(prompt)-8, attr=colors[options.color_edit_cell], unprintablechar=options.disp_unprintable, **kwargs)
    vd().inInput = False
    return ret

def confirm(prompt):
    yn = input(prompt, value='n')[:1]
    if not yn or yn not in 'Yy':
        error('disconfirmed')

import unicodedata
def clipstr(s, dispw):
    '''Return clipped string and width in terminal display characters.

    Note: width may differ from len(s) if East Asian chars are 'fullwidth'.'''
    w = 0
    ret = ''
    ambig_width = options.disp_ambig_width
    for c in s:
        if c != ' ' and unicodedata.category(c) in ('Cc', 'Zs', 'Zl'):  # control char, space, line sep
            ret += options.disp_oddspace
            w += len(options.disp_oddspace)
        else:
            ret += c
            eaw = unicodedata.east_asian_width(c)
            if eaw == 'A':  # ambiguous
                w += ambig_width
            elif eaw in 'WF': # wide/full
                w += 2
            elif not unicodedata.combining(c):
                w += 1

        if w > dispw-len(options.disp_truncator)+1:
            ret = ret[:-2] + options.disp_truncator  # replace final char with ellipsis
            w += len(options.disp_truncator)
            break

    return ret, w


## Built-in sheets
class TextColumn(Column):
    'TextColumn always uses the terminal width'
    @property
    def width(self):
        return vd().windowWidth

    @width.setter
    def width(self, v):
        pass

## text viewer and dir browser
class TextSheet(Sheet):
    'Sheet displaying a string (one line per row) or a list of strings.'

    @async
    def reload(self):
        self.columns = [TextColumn(self.name, getter=lambda r: r[1])]
        self.rows = []
        if isinstance(self.source, list):
            for x in self.genProgress(self.source):
                # copy so modifications don't change 'original'; also one iteration through generator
                self.addLine(x)
        elif isinstance(self.source, str):
            for L in self.genProgress(self.source.splitlines()):
                self.addLine(L)
        elif isinstance(self.source, io.IOBase):
            for L in readlines(self.source):
                self.addLine(L)
        elif isinstance(self.source, Path):
            self.progressMade = 0
            self.progressTotal = self.source.filesize
            with self.source.open_text() as fp:
                for L in readlines(fp):
                    self.addLine(L)
                    self.progressMade += len(L)
        else:
            error('unknown text type ' + str(type(self.source)))

    def addLine(self, text):
        'Handle text re-wrapping.'
        if options.textwrap:
            startingLine = len(self.rows)
            for i, L in enumerate(textwrap.wrap(text, width=self.vd.windowWidth-2)):
                self.addRow((startingLine+i, L))
        else:
            self.addRow((len(self.rows), text))

class ColumnsSheet(Sheet):
    columns = [
            ColumnAttr('sheet', width=0),
            ColumnAttr('name'),
            ColumnAttr('width', type=int),
            ColumnEnum('type', globals(), default=anytype),
            ColumnAttr('fmtstr'),
            Column('value', full_getter=lambda self,c,r: r.getDisplayValue(self.source.cursorRow)),
    ]
    colorizers = [
            Colorizer('row', 8, lambda self,c,r,v: options.color_key_col if r in self.source.keyCols else None)
    ]

    def reload(self):
        self.rows = self.source.columns
        self.cursorRowIndex = self.source.cursorColIndex


class SheetsSheet(Sheet):
    commands = [Command(ENTER, 'moveListItem(vd.sheets, cursorRowIndex, 0); vd.sheets.pop(1)', 'jump to this sheet')]
    columns = [ColumnAttr(name) for name in 'name nRows nCols nVisibleCols cursorDisplay keyColNames source'.split()]

    def reload(self):
        self.rows = vd().sheets


class HelpSheet(Sheet):
    'Show all commands available to the source sheet.'
    columns = [ColumnItem('keystrokes', 0),
               ColumnItem('action', 1),
               Column('with_g_prefix', full_getter=lambda s,c,r: s.source._commands.get('g'+r[0], (None,'-'))[1]),
               ColumnItem('execstr', 2, width=0),
    ]
    nKeys = 1
    def reload(self):
        self.rows = []
        for src in self.source._commands.maps:
            self.rows.extend(src.values())


class OptionsSheet(Sheet):
    commands = [Command(ENTER, 'source[cursorRow[0]] = editCell(1)', 'edit this option')]
    columns = [ColumnItem('option', 0),
               Column('value', getter=lambda r:r[1], setter=lambda s,c,r,v: setattr(options, r[0], v)),
               ColumnItem('default', 2),
               ColumnItem('description', 3)]
    colorizers = []
    nKeys = 1

    def reload(self):
        self.rows = list(self.source._opts.values())

vd().optionsSheet = OptionsSheet('options', options)

# A .. Z AA AB .. ZY ZZ  (max 702 unnamed columns)
defaultColNames = list(string.ascii_uppercase) + list(''.join(j) for j in itertools.product(string.ascii_uppercase, repeat=2))

### Curses helpers

def _clipdraw(scr, y, x, s, attr, w):
    'Draw string `s` at (y,x)-(y,x+w), clipping with ellipsis char.'
    _, windowWidth = scr.getmaxyx()
    dispw = 0
    try:
        if w is None:
            w = windowWidth-1
        w = min(w, windowWidth-x-1)
        if w == 0:  # no room anyway
            return

        # convert to string just before drawing
        s, dispw = clipstr(str(s), w)
        scr.addstr(y, x, options.disp_column_fill*w, attr)
        scr.addstr(y, x, s, attr)
    except Exception as e:
#        raise type(e)('%s [clip_draw y=%s x=%s dispw=%s w=%s]' % (e, y, x, dispw, w)
#                ).with_traceback(sys.exc_info()[2])
        pass

# https://stackoverflow.com/questions/19833315/running-system-commands-in-python-using-curses-and-panel-and-come-back-to-previ
class suspend_curses():
    'Context Manager to temporarily leave curses mode'
    def __enter__(self):
        curses.endwin()

    def __exit__(self, exc_type, exc_val, tb):
        newscr = curses.initscr()
        newscr.refresh()
        curses.doupdate()

def editText(scr, y, x, w, attr=curses.A_NORMAL, value='', fillchar=' ', truncchar='-', unprintablechar='.', completer=lambda text,idx: None, history=[], display=True):
    'A better curses line editing widget.'

    def until_get_wch():
        'Ignores get_wch timeouts'
        ret = None
        while not ret:
            try:
                ret = scr.get_wch()
            except _curses.error:
                pass

        return ret

    def splice(v, i, s):
        'Insert `s` into string `v` at `i` (such that v[i] == s[0]).'
        return v if i < 0 else v[:i] + s + v[i:]

    def clean_printable(s):
        'Escape unprintable characters.'
        return ''.join(c if c.isprintable() else ('<%04X>' % ord(c)) for c in str(s))

    def delchar(s, i, remove=1):
        'Delete `remove` characters from str `s` beginning at position `i`.'
        return s if i < 0 else s[:i] + s[i+remove:]

    def complete(v, comps, cidx):
        'Complete keystroke `v` based on list `comps` of completions.'
        if comps:
            for i in range(cidx, cidx + len(comps)):
                i %= len(comps)
                if comps[i].startswith(v):
                    return comps[i]
        # beep
        return v

    def launchExternalEditor(v):
        editor = os.environ.get('EDITOR') or error('$EDITOR not set')

        import tempfile
        fd, fqpn = tempfile.mkstemp(text=True)
        with open(fd, 'w') as fp:
            fp.write(v)

        with suspend_curses():
            os.system('%s %s' % (editor, fqpn))

        with open(fqpn, 'r') as fp:
            return fp.read()

    insert_mode = True
    first_action = True
    v = str(value)  # value under edit
    i = 0           # index into v
    comps_idx = -1
    hist_idx = 0
    left_truncchar = right_truncchar = truncchar

    while True:
        if display:
            dispval = clean_printable(v)
        else:
            dispval = '*' * len(v)

        dispi = i  # the onscreen offset within the field where v[i] is displayed
        if len(dispval) < w:  # entire value fits
            dispval += fillchar*(w-len(dispval))
        elif i == len(dispval):  # cursor after value (will append)
            dispi = w-1
            dispval = left_truncchar + dispval[len(dispval)-w+2:] + fillchar
        elif i >= len(dispval)-w//2:  # cursor within halfwidth of end
            dispi = w-(len(dispval)-i)
            dispval = left_truncchar + dispval[len(dispval)-w+1:]
        elif i <= w//2:  # cursor within halfwidth of beginning
            dispval = dispval[:w-1] + right_truncchar
        else:
            dispi = w//2  # visual cursor stays right in the middle
            k = 1 if w%2==0 else 0  # odd widths have one character more
            dispval = left_truncchar + dispval[i-w//2+1:i+w//2-k] + right_truncchar

        scr.addstr(y, x, dispval, attr)
        scr.move(y, x+dispi)
        ch = vd().getkeystroke(scr)
        if ch == '':                               continue
        elif ch == 'KEY_IC':                       insert_mode = not insert_mode
        elif ch == '^A' or ch == 'KEY_HOME':       i = 0
        elif ch == '^B' or ch == 'KEY_LEFT':       i -= 1
        elif ch == '^C' or ch == ESC:              raise EscapeException(ch)
        elif ch == '^D' or ch == 'KEY_DC':         v = delchar(v, i)
        elif ch == '^E' or ch == 'KEY_END':        i = len(v)
        elif ch == '^F' or ch == 'KEY_RIGHT':      i += 1
        elif ch in ('^H', 'KEY_BACKSPACE', '^?'):  i -= 1; v = delchar(v, i)
        elif ch == '^I':                           comps_idx += 1; v = completer(v[:i], comps_idx) or v
        elif ch == 'KEY_BTAB':                     comps_idx -= 1; v = completer(v[:i], comps_idx) or v
        elif ch == ENTER:                          break
        elif ch == '^K':                           v = v[:i]  # ^Kill to end-of-line
        elif ch == '^R':                           v = str(value)  # ^Reload initial value
        elif ch == '^T':                           v = delchar(splice(v, i-2, v[i-1]), i)  # swap chars
        elif ch == '^U':                           v = v[i:]; i = 0  # clear to beginning
        elif ch == '^V':                           v = splice(v, i, until_get_wch()); i += 1  # literal character
        elif ch == '^Z':                           v = launchExternalEditor(v)
        elif history and ch == 'KEY_UP':           hist_idx += 1; v = history[hist_idx % len(history)]
        elif history and ch == 'KEY_DOWN':         hist_idx -= 1; v = history[hist_idx % len(history)]
        elif ch.startswith('KEY_'):                pass
        else:
            if first_action:
                v = ''
            if insert_mode:
                v = splice(v, i, ch)
            else:
                v = v[:i] + ch + v[i+1:]

            i += 1

        if i < 0: i = 0
        if i > len(v): i = len(v)
        first_action = False

    return v


class ColorMaker:
    def __init__(self):
        self.attrs = {}
        self.color_attrs = {}

    def setup(self):
        self.color_attrs['black'] = curses.color_pair(0)

        for c in range(0, int(options.num_colors) or curses.COLORS):
            curses.init_pair(c+1, c, curses.COLOR_BLACK)
            self.color_attrs[str(c)] = curses.color_pair(c+1)

        for c in 'red green yellow blue magenta cyan white'.split():
            colornum = getattr(curses, 'COLOR_' + c.upper())
            self.color_attrs[c] = curses.color_pair(colornum+1)

        for a in 'normal blink bold dim reverse standout underline'.split():
            self.attrs[a] = getattr(curses, 'A_' + a.upper())

    def keys(self):
        return list(self.attrs.keys()) + list(self.color_attrs.keys())

    def __getitem__(self, colornamestr):
        color, prec = self.update(0, 0, colornamestr, 10)
        return color

    def update(self, attr, attr_prec, colornamestr, newcolor_prec):
        attr = attr or 0
        if isinstance(colornamestr, str):
            for colorname in colornamestr.split(' '):
                if colorname in self.color_attrs:
                    if newcolor_prec > attr_prec:
                        attr &= ~2047
                        attr |= self.color_attrs[colorname.lower()]
                        attr_prec = newcolor_prec
                elif colorname in self.attrs:
                    attr |= self.attrs[colorname.lower()]
        return attr, attr_prec


colors = ColorMaker()

def setupcolors(stdscr, f, *args):
    curses.raw()    # get control keys instead of signals
    curses.meta(1)  # allow "8-bit chars"
#    curses.mousemask(curses.ALL_MOUSE_EVENTS)  # enable mouse events
#    curses.mouseinterval(0)
    return f(stdscr, *args)

def wrapper(f, *args):
    return curses.wrapper(setupcolors, f, *args)

### external interface

class Path:
    'File and path-handling class, modeled on `pathlib.Path`.'
    def __init__(self, fqpn):
        self.fqpn = fqpn
        fn = os.path.split(fqpn)[-1]

        # check if file is gzip-compressed
        if fn.endswith('.gz'):
            self.gzip_compressed = True
            fn = fn[:-3]
        else:
            self.gzip_compressed = False

        self.name, self.ext = os.path.splitext(fn)
        self.suffix = self.ext[1:]

    def open_text(self, mode='r'):
        if self.gzip_compressed:
            return gzip.open(self.resolve(), mode='rt', encoding=options.encoding, errors=options.encoding_errors)
        else:
            return open(self.resolve(), mode=mode, encoding=options.encoding, errors=options.encoding_errors)

    def readlines(self):
        for i, line in enumerate(self.open_text()):
            if i < options.skiplines:
                continue
            yield line[:-1]

    def read_text(self):
        with self.open_text() as fp:
            return fp.read()

    def read_bytes(self):
        with open(self.resolve(), 'rb') as fp:
            return fp.read()

    def is_dir(self):
        return os.path.isdir(self.resolve())

    def exists(self):
        return os.path.exists(self.resolve())

    def iterdir(self):
        return [self.parent] + [Path(os.path.join(self.fqpn, f)) for f in os.listdir(self.resolve())]

    def stat(self):
        try:
            return os.stat(self.resolve())
        except:
            return None

    def resolve(self):
        'Resolve pathname shell variables and ~userdir'
        return os.path.expandvars(os.path.expanduser(self.fqpn))

    def relpath(self, start):
        return os.path.relpath(os.path.realpath(self.resolve()), start)

    @property
    def parent(self):
        'Return Path to parent directory.'
        return Path(self.fqpn + "/..")

    @property
    def filesize(self):
        return self.stat().st_size

    def __str__(self):
        return self.fqpn

class UrlPath:
    def __init__(self, url):
        from urllib.parse import urlparse
        self.url = url
        self.obj = urlparse(url)
        self.name = self.obj.netloc

    def __str__(self):
        return self.url

    def __getattr__(self, k):
        return getattr(self.obj, k)


class PathFd(Path):
    'minimal Path interface to satisfy a tsv loader'
    def __init__(self, pathname, fp, filesize=0):
        super().__init__(pathname)
        self.fp = fp
        self.alreadyRead = []  # shared among all RepeatFile instances
        self._filesize = filesize

    def read_text(self):
        return self.fp.read()

    def open_text(self):
        return RepeatFile(self)

    @property
    def filesize(self):
        return self._filesize


class RepeatFile:
    def __init__(self, pathfd):
        self.pathfd = pathfd
        self.iter = None

    def __enter__(self):
        self.iter = RepeatFileIter(self)
        return self

    def __exit__(self, a,b,c):
        pass

    def __iter__(self):
        return RepeatFileIter(self)

    def __next__(self):
        return next(self.iter)

class RepeatFileIter:
    def __init__(self, rf):
        self.rf = rf
        self.nextIndex = 0

    def __iter__(self):
        return RepeatFileIter(self.rf)

    def __next__(self):
        if self.nextIndex < len(self.rf.pathfd.alreadyRead):
            r = self.rf.pathfd.alreadyRead[self.nextIndex]
        else:
            r = next(self.rf.pathfd.fp)
            self.rf.pathfd.alreadyRead.append(r)

        self.nextIndex += 1
        return r


def run(sheetlist=[]):
    'Main entry point; launches vdtui with the given sheets already pushed (last one is visible)'

    # reduce ESC timeout to 25ms. http://en.chys.info/2009/09/esdelay-ncurses/
    os.putenv('ESCDELAY', '25')

    ret = wrapper(cursesMain, sheetlist)
    if ret:
        print(ret)

def cursorEnable(b):
    try:
        curses.curs_set(1 if b else 0)
    except:
        pass

def cursesMain(_scr, sheetlist=[]):
    'Populate VisiData object with sheets from a given list.'

    colors.setup()

    for vs in sheetlist:
        vd().push(vs)  # first push does a reload

    status('<F1> or z? opens help')
    return vd().run(_scr)

def addGlobals(g):
    'importers can call `addGlobals(globals())` to have their globals accessible to execstrings'
    globals().update(g)

def getGlobals():
    return globals()

if __name__ == '__main__':
    run(TextSheet('contents', Path(src)) for src in sys.argv[1:])
