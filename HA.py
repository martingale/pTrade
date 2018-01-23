from pyalgotrade import technical
from pyalgotrade.dataseries import bards
import numpy as np

class HADirEventWindow():
    def __init__(self, period, useAdjustedValues):
        assert(period >= 1)
        self.__period = period
        self.__useAdjustedValues = useAdjustedValues
        self.__prevClose = None
        self.__value = [None, None]
        self.__n = 0
        self.__op = []
        self.__cl = []
        self.__open = technical.EventWindow(period)
        self.__close = technical.EventWindow(period)

    def _getClose(self, value):
        return value.getClose(self.__useAdjustedValues)

    def _getOpen(self, value):
        return value.getOpen(self.__useAdjustedValues)

    def onNewValue(self, dateTime, value):
        op = self._getOpen(value)
        cl = self._getClose(value)
        self.__open.onNewValue(dateTime, op)
        self.__close.onNewValue(dateTime, cl)
        self.__prevClose = value.getClose(self.__useAdjustedValues)

        if value is not None and self.__open.windowFull() and self.__close.windowFull():
            if self.__period > 1:
                for i in range(2, self.__period+1):
                    open_values = self.__open.getValues()[-i:-1]
                    close_values = self.__close.getValues()[-i:-1]
                    open_values = self.__open.getValues()[-i:-(i-1)]
                    close_values = self.__close.getValues()[-i:-(i-1)]
                    values = np.append(open_values, close_values)
                    max_val = max(values)
                    min_val = min(values)

                    if op >= min_val and op <= max_val and cl >= min_val and cl <= max_val:
                        if close_values[0] > open_values[0]:
                            self.__value = [1, i-1]
                        else:
                            self.__value = [-1, i-1]
                        break
                    else:
                        if cl > op:
                            self.__value = [1, 0]
                        else:
                            self.__value = [-1, 0]

            elif self.__period == 1:
                if cl > op:
                    self.__value = [1, 0]
                else:
                    self.__value = [-1, 0]

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

    def __init__(self, barDataSeries, period, useAdjustedValues=False, maxLen=None):
        if not isinstance(barDataSeries, bards.BarDataSeries):
            raise Exception("barDataSeries must be a dataseries.bards.BarDataSeries instance")

        super(HADir, self).__init__(barDataSeries, HADirEventWindow(period, useAdjustedValues), maxLen)
