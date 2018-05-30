from pyalgotrade import technical
from pyalgotrade.dataseries import bards
from pandas.tseries.offsets import BMonthEnd
import numpy as np

class HADirEventWindow():
    def __init__(self, useAdjustedValues, maxLen):
        # assert(period >= 1)
        # self.__period = period
        self.__useAdjustedValues = useAdjustedValues
        self.__prevClose = None
        self.__prevOpen = None

        self.__prev_bar = None
        self.__prev_datetime = None

        self.__value = [None, None]
        self.__prev_values = []
        self.__n = 0
        self.__op = []
        self.__cl = []
        self.openDS = technical.EventWindow(maxLen)
        self.highDS = technical.EventWindow(maxLen)
        self.lowDS = technical.EventWindow(maxLen)
        self.closeDS = technical.EventWindow(maxLen)
        self.month_openDS = technical.EventWindow(1)
        self.month_closeDS = technical.EventWindow(1)

    def _getClose(self, value):
        return value.getClose(self.__useAdjustedValues)

    def _getOpen(self, value):
        return value.getOpen(self.__useAdjustedValues)

    def _getHigh(self, value):
        return value.getHigh(self.__useAdjustedValues)

    def _getLow(self, value):
        return value.getLow(self.__useAdjustedValues)

    def _getExtra(self, value):
        return value.getExtraColumns()

    def onNewValue(self, dateTime, value, lastFlag):
        op = self._getOpen(value)
        cl = self._getClose(value)
        hg = self._getHigh(value)
        lw = self._getLow(value)
        extra = self._getExtra(value)['realTime']

        if str(extra) == '1998-04-30 00:00:00':
            pass

        if self.month_openDS.getLength() > 0:
            ha_close = (op + hg + lw + cl) / 4.0
            ha_open = (self.month_openDS.getValues()[-1] + self.month_closeDS.getValues()[-1]) / 2.0
            ha_low = min([lw, ha_open, ha_close])
            ha_high = max([hg, ha_open, ha_close])
        else:
            ha_close = (op + hg + lw + cl) / 4.0
            ha_open = (op + cl) / 2.0
            ha_low = lw
            ha_high = hg

        self.__prev_datetime = dateTime
        self.openDS.onNewValue(dateTime, ha_open, False)
        self.closeDS.onNewValue(dateTime, ha_close, False)
        self.__prevClose = value.getClose(self.__useAdjustedValues)
        self.__prev_bar = value

        self.__value = {'haOpen': round(ha_open, 2), 'haClose': round(ha_close, 2)}
        # if value is not None and self.openDS.windowFull() and self.closeDS.windowFull():
        #     if self.__period > 1:
        #         # for i in range(2, self.__period + 1): # nearest bar
        #         for i in range(self.__period, 1, -1): # farthest bar
        #             # Look for range
        #             # open_values = self.__open.getValues()[-i:-1]
        #             # close_values = self.__close.getValues()[-i:-1]
        #             # Look for one bar
        #             open_values = self.openDS.getValues()[-i:-(i - 1)]
        #             close_values = self.closeDS.getValues()[-i:-(i - 1)]
        #             prev_values = self.__prev_values[-i:-(i-1)]
        #             values = np.append(open_values, close_values)
        #             max_val = max(values)
        #             min_val = min(values)
        #
        #             # if op >= min_val and op <= max_val and cl >= min_val and cl <= max_val:
        #             #     if close_values[0] > open_values[0]:
        #             #         self.__value = [1, i-1]
        #             #         self.__prev_values.append(1)
        #             #     else:
        #             #         self.__value = [-1, i-1]
        #             #         self.__prev_values.append(-1)
        #             #     # self.__value = [prev_values[0], i-1]
        #             #     # self.__prev_values.append(self.__value[0])
        #             #     break
        #             # else:
        #             #     if cl > op:
        #             #         self.__value = [1, 0]
        #             #         self.__prev_values.append(1)
        #             #     else:
        #             #         self.__value = [-1, 0]
        #             #         self.__prev_values.append(1)
        #
        #             #######################################
        #
        #             if ha_open >= min_val and ha_open <= max_val and ha_close >= min_val and ha_close <= max_val:
        #                 if cl > op:
        #                     self.__value = [1, i-1, ha_open, ha_high, ha_low, ha_close]
        #                 else:
        #                     self.__value = [-1, i-1, ha_open, ha_high, ha_low, ha_close]
        #                 # self.__value = [prev_values[0], i-1]
        #                 # self.__prev_values.append(self.__value[0])
        #                 break
        #             else:
        #                 if ha_close > ha_open:
        #                     self.__value = [1, 0, ha_open, ha_high, ha_low, ha_close]
        #                 else:
        #                     self.__value = [-1, 0, ha_open, ha_high, ha_low, ha_close]
        #
        #     elif self.__period == 1:
        #         if ha_close > ha_open:
        #             self.__value = [1, 0, ha_open, ha_high, ha_low, ha_close]
        #         else:
        #             self.__value = [-1, 0, ha_open, ha_high, ha_low, ha_close]

        if BMonthEnd().rollforward(extra).date() == extra.date() and str(extra.time()) == '23:00:00' and self.__prev_datetime is not None:
            self.month_openDS.onNewValue(dateTime, self.openDS.getValues()[-1], lastFlag)
            self.month_closeDS.onNewValue(dateTime, self.closeDS.getValues()[-1], lastFlag)

    def getValue(self):
        return self.__value

class HADir(technical.EventBasedFilter):
    """Average True Range filter as described in http://stockcharts.com/school/doku.php?id=chart_school:technical_indicators:average_true_range_atr

    :param barDataSeries: The BarDataSeries instance being filtered.
    :type barDataSeries: :class:`pyalgotrade.dataseries.bards.BarDataSeries`.
    :param period: The average period. Must be > 1.
    :type period: int.
    :param useAdjustedValues: True to use adjusted Low/High/Close values.
    :type useAdjustedValues: boolean.
    :param maxLen: The maximum number of values to hold.
        Once a bounded length is full, when new items are added, a corresponding number of items are discarded from the
        opposite end. If None then dataseries.DEFAULT_MAX_LEN is used.
    :type maxLen: int.
    """

    def __init__(self, barDataSeries, useAdjustedValues=False, maxLen=1024):
        # if not isinstance(barDataSeries, bards.BarDataSeries):
        #     raise Exception("barDataSeries must be a dataseries.bards.BarDataSeries instance")

        super(HADir, self).__init__(barDataSeries, HADirEventWindow(useAdjustedValues, maxLen), maxLen)
