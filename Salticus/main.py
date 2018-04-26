from pyalgotrade import strategy
from pyalgotrade import plotter
from pyalgotrade.stratanalyzer import returns
from pyalgotrade import dataseries
from pyalgotrade.stratanalyzer import sharpe
from pyalgotrade import bar
from pyalgotrade import barfeed
from pyalgotrade.barfeed import csvfeed
from pyalgotrade.utils import csvutils
from pyalgotrade.stratanalyzer import trades
import datetime
import time
from pyalgotrade.technical import ma
import HA as ha
from pandas.tseries.offsets import BMonthEnd
import numpy as np
import itertools
from pyalgotrade.optimizer import local

class RowParser(csvfeed.RowParser):
    def __init__(self):
        self.__prevClose = None
        self.__prevOpen = None

    def getFieldNames(self):
        # It is expected for the first row to have the field names.
        return None

    def getDelimiter(self):
        return ","

    def parseBar(self, csvRowDict):

        #dateTime = datetime.datetime.strptime(csvRowDict["Date Time"], "%Y-%m-%d %H:%M:%S")
        bar_date = datetime.datetime.strptime(csvRowDict["Date"], "%m/%d/%Y") #- datetime.timedelta(days=1) #05/06/1998,00:00
        bar_time = datetime.datetime.strptime(csvRowDict["Time"], "%H:%M") #05/06/1998,00:00
        bar_time = datetime.datetime.strptime('23:00', "%H:%M") #05/06/1998,00:00

        dateTime = datetime.datetime.combine(bar_date.date(), bar_time.time() )
        open = float(csvRowDict["Open"])
        high = float(csvRowDict["High"])
        low = float(csvRowDict["Low"])
        close = float(csvRowDict["Close"])
        ha_close = sum([open, high, low, close]) / 4.0

        if self.__prevClose is None and self.__prevOpen is None:
            ha_open = (open + close)/2.0
            ha_low = low
            ha_high = high
        else:
            ha_open = (self.__prevOpen + self.__prevClose)/2.0
            ha_low  = min([low, ha_open, ha_close])
            ha_high = max([high, ha_open, ha_close])

        ha_volume = float(csvRowDict["Vol"])
        ha_bar = bar.BasicBar(dateTime, ha_open, ha_high, ha_low, ha_close, ha_volume, ha_close, None)
        bar_ = bar.BasicBar(dateTime, open, high, low, close, ha_volume, close, None)
        self.__prevClose = ha_close
        self.__prevOpen = ha_open

        # return bar_, ha_bar
        return bar_

class Bars(csvfeed.BarFeed):
    def __init__(self, frequency=bar.Frequency.DAY, maxLen=1024):
        super(Bars, self).__init__(frequency, maxLen)

    def barsHaveAdjClose(self):
        return False

    def addBarsFromCSV(self, instrument, path, row_parser):
        rowParser = RowParser()
        super(Bars, self).addBarsFromCSV(instrument, path, rowParser)

class Strategy(strategy.BacktestingStrategy):
    def __init__(self, feed, instrument1, instrument2, sma_period1, sma_period2, buy_diff, sell_diff):
        super(Strategy, self).__init__(feed)
        self.__instrument1 = instrument1
        self.__instrument2 = instrument2

        self._prices1 = feed[self.__instrument1].getCloseDataSeries()
        self._prices2 = feed[self.__instrument2].getCloseDataSeries()

        self.__sma1 = ma.SMA(self._prices1, sma_period1)
        self.__sma2 = ma.SMA(self._prices2, sma_period2)

        self.__buy_diff = buy_diff
        self.__sell_diff = sell_diff

        self._longposition = None
        self._shortposition = None

    def onEnterCanceled(self, position):
        if self._longposition == position:
            self._longposition = None
        elif self._shortposition == position:
            self._shortposition = None
        else:
            assert False

    def onExitOk(self, position):
        if self._longposition == position:
            self._longposition = None
            self._stopLossOrder = None
            self.__execInfo = str(position.getExitOrder().getAvgFillPrice()) + ", LX"
        elif self._shortposition == position:
            self._shortposition = None
            self._stopLossOrder = None
            self.__execInfo = str(position.getExitOrder().getAvgFillPrice()) + ", SX"

        self.info(self.__execInfo)

    # def onExitCanceled(self, position):
    #     # If the exit was canceled, re-submit it.
    #     if self._longposition == position:
    #         self._longposition.exitMarket()
    #     elif self._shortposition == position:
    #         self._shortposition.exitMarket()
    #     else:
    #         assert False

    def onEnterOk(self, position):
        if position.getEntryOrder().isBuy():
            exec_info = str(position.getEntryOrder().getAvgFillPrice()) + ", LE"
        else:
            exec_info = str(position.getEntryOrder().getAvgFillPrice()) + ", SE"

        self.info(exec_info)

    def enterLongSignal(self, x, y):
        cond = x[0] == y[0] == 1
        return cond

    def enterShortSignal(self, x, y):
        cond = x[0] == y[0] == -1
        return cond

    def onBars(self, bars):
        sma1 = self.__sma1
        sma2 = self.__sma2

        if sma1[-1] is None or sma2[-1] is None:
            return

        percent_change1 = ((self._prices1[-1] - sma1[-1]) / sma1[-1]) * 100
        percent_change2 = ((self._prices2[-1] - sma2[-1]) / sma2[-1]) * 100

        diff = percent_change1 - percent_change2
        # self.info(str(bars.getDateTime()) + ' ' + '%.2f' % diff)
        shares = 100

        if self._longposition is None and self._shortposition is None:
            if diff > self.__buy_diff:
                self._longposition = self.enterLong(self.__instrument1, shares, True)
            elif diff < self.__sell_diff:
                self._shortposition = self.enterShort(self.__instrument1, shares, True)
        elif self._longposition is not None:
            if diff < self.__buy_diff:
                if not self._longposition.exitActive():
                    self._longposition.exitMarket()
        elif self._shortposition is not None:
            if diff > self.__sell_diff:
                if not self._shortposition.exitActive():
                    self._shortposition.exitMarket()

def main(plot):
    instrument1 = "SPX"
    instrument2 = "VIX"

    path1 = 'SPX.X_daily_OHLC_041698-041618.txt'
    path2 = 'VIX.X_daily_OHLC_041698-041618.txt'

    feed = Bars()
    feed.addBarsFromCSV(instrument1, path1, RowParser)
    feed.addBarsFromCSV(instrument2, path2, RowParser)

    strat = Strategy(feed, instrument1, instrument2, 200, 200, -90, 30)

    # strat.run()

    sharpeRatioAnalyzer = sharpe.SharpeRatio()
    strat.attachAnalyzer(sharpeRatioAnalyzer)
    #
    tradesAnalyzer = trades.Trades()
    strat.attachAnalyzer(tradesAnalyzer)
    #
    retAnalyzer = returns.Returns()
    strat.attachAnalyzer(retAnalyzer)

    if plot:
        plt = plotter.StrategyPlotter(strat, True, True, True)
        # plt.getInstrumentSubplot(instrument).addDataSeries("upper", strat.getBollingerBands_upper.getUpperBand())
        # plt.getInstrumentSubplot(instrument).addDataSeries("middle", strat.getBollingerBands().getMiddleBand())
        # plt.getInstrumentSubplot(instrument).addDataSeries("lower", strat.getBollingerBands_lower.getLowerBand())
    start_time = time.time()  # taking current time as starting time
    strat.run()
    elapsed_time = time.time() - start_time
    print("Time elapsed: %.4f seconds" % elapsed_time)

    print("Sharpe ratio: %.4f" % sharpeRatioAnalyzer.getSharpeRatio(0.008))
    print "Final portfolio value: $%.2f" % strat.getBroker().getEquity()
    print retAnalyzer.
    print tradesAnalyzer.getCount()

    if plot:
        plt.plot()


if __name__ == "__main__":
    main(True)


# def parameters_generator():
#     buy_diff = range(-150, 50, 10)
#     sell_diff = range(-50, 50, 10)
#     return itertools.product(['SPX'], ['VIX'], [200], [200], buy_diff, sell_diff)
#
#
# # The if __name__ == '__main__' part is necessary if running on Windows.
# if __name__ == '__main__':
#     instrument1 = "SPX"
#     instrument2 = "VIX"
#
#     path1 = 'SPX.X_daily_OHLC_041698-041618.txt'
#     path2 = 'VIX.X_daily_OHLC_041698-041618.txt'
#
#     feed = Bars()
#     feed.addBarsFromCSV(instrument1, path1, RowParser)
#     feed.addBarsFromCSV(instrument2, path2, RowParser)
#
#     local.run(Strategy, feed, parameters_generator())
