
from visidata import *

command('F', 'vd.push(SheetFreqTable(sheet, cursorCol))', 'open frequency table from values in this column')
command('gF', 'vd.push(SheetFreqTable(sheet, combineColumns(columns[:nKeys])))', 'open frequency table for the combined key columns')

theme('disp_histogram', '*')
option('disp_histolen', 80, 'width of histogram column')
option('histogram_bins', 0, 'number of bins for histogram of numeric columns')


class SheetFreqTable(Sheet):
    'Generate frequency-table sheet on currently selected column.'
    def __init__(self, sheet, col):
        fqcolname = '%s_%s_freq' % (sheet.name, col.name)
        super().__init__(fqcolname, sheet)
        self.origCol = col
        self.largest = 100

        self.columns = [
            ColumnItem(col.name, 0, type=col.type, width=30),
            Column('num', int, lambda r: len(r[1])),
            Column('percent', float, lambda r: len(r[1])*100/self.source.nRows),
            Column('histogram', str, lambda r,s=self: options.disp_histogram*(options.disp_histolen*len(r[1])//s.largest), width=None)
        ]

        for c in self.source.visibleCols:
            if c.aggregator:
                self.columns.append(Column(c.aggregator.__name__+'_'+c.name,
                                           type=c.aggregator.type or c.type,
                                           getter=lambda r,c=c: c.aggregator(c.values(r[1]))))

        self.nKeys = 1

        # redefine these commands only to change the helpstr
        self.command(' ', 'toggle([cursorRow]); cursorDown(1)', 'toggle these entries in the source sheet')
        self.command('s', 'select([cursorRow]); cursorDown(1)', 'select these entries in the source sheet')
        self.command('u', 'unselect([cursorRow]); cursorDown(1)', 'unselect these entries in the source sheet')

        self.command(ENTER, 'vd.push(source.copy("_"+cursorRow[0])).rows = cursorRow[1].copy()', 'push new sheet with only source rows for this value')

    def selectRow(self, row):
        self.source.select(row[1])     # select all entries in the bin on the source sheet
        return super().selectRow(row)  # then select the bin itself on this sheet

    def unselectRow(self, row):
        self.source.unselect(row[1])
        return super().unselectRow(row)

    @async
    def reload(self):
        'Generate histrow for each row and then reverse-sort by length.'
        rowidx = {}
        self.rows = []

        nbins = options.histogram_bins or int(len(self.source.rows) ** (1./3))

        if nbins and self.origCol.type in (int, float, currency):
            self.columns[0]._type = str

            # separate rows with errors at the column from those without errors
            errorbin = []
            allbin = []
            for row in self.genProgress(self.source.rows):
                v = self.origCol.getDisplayValue(row)
                if not v:
                    errorbin.append(row)
                else:
                    allbin.append((self.origCol.getValue(row), row))

            # find bin pivots from non-error values
            binPivots = []

            sortedValues = sorted(allbin)
            binsize = len(sortedValues)//nbins
            for binIdx, firstIdx in enumerate(self.genProgress(range(0, len(sortedValues), binsize))):
                firstVal = self.origCol.getValue(sortedValues[firstIdx][1])

                binPivots.append(firstVal)

            # put rows into bins (as self.rows) based on values
            binMinIdx = 0
            binMinVal = self.origCol.getDisplayValue(sortedValues[binMinIdx][1])

            for binMax in binPivots[1:]:
                binrows = []
                for i, (v, row) in enumerate(sortedValues[binMinIdx:]):
                    if v > binMax:
                        break
                    binrows.append(row)

                binMaxVal = self.origCol.getDisplayValue(row)  # last row before break
                if binMinIdx == 0:
                    binName = '<=[%s-]%s' % (binMinVal, binMaxVal)
                elif binMax == binPivots[-1]:
                    binName = '>=%s[-%s]' % (binMinVal, binMaxVal)
                    binrows.append(row)
                else:
                    binName = '%s-%s' % (binMinVal, binMaxVal)

                self.rows.append((binName, binrows))
                binMinIdx += i
                binMinVal = self.origCol.getDisplayValue(row)

            if errorbin:
                self.rows.append(('errors', errorbin))

            sync()
        else:
            for r in self.genProgress(self.source.rows):
                v = str(self.origCol.getValue(r))
                histrow = rowidx.get(v)
                if histrow is None:
                    histrow = (v, [])
                    rowidx[v] = histrow
                    self.rows.append(histrow)
                histrow[1].append(r)

            self.rows.sort(key=lambda r: len(r[1]), reverse=True)  # sort by num reverse
        self.largest = len(self.rows[0][1])+1
