import pandas as pd
import numpy as np
from pyalgotrade import dataseries
from pyalgotrade import strategy
from pyalgotrade import barfeed
from pyalgotrade.broker import backtesting
from pyalgotrade.barfeed import csvfeed
from pyalgotrade import bar
from pyalgotrade.technical import cross
from pyalgotrade.technical import ma
from pyalgotrade.stratanalyzer import sharpe
from pyalgotrade.stratanalyzer import trades


from datetime import datetime
import time
from joblib import Parallel, delayed
from pyalgotrade.utils import csvutils


class RowParser(csvfeed.RowParser):
    def __init__(self):
        self.__prevClose = None
        self.__tradeprices = []
        self.__lasttimestamp = None
        self.__volume = None

    def getFieldNames(self):
        # It is expected for the first row to have the field names.
        return None

    def getDelimiter(self):
        return ","

    def parseBar(self, csvRowDict, bar_period):
        timestamp = datetime.strptime(csvRowDict["date_time"], "%Y-%m-%d %H:%M:%S.%f")
        volume = 10000000
        isnew = False
        if self.__lasttimestamp is None:
            isnew = True
        else:
            d1_ts = time.mktime(timestamp.timetuple())
            d2_ts = time.mktime(self.__lasttimestamp.timetuple())
            cond1 = (d1_ts % (bar_period * 60)) - (d2_ts % (bar_period * 60)) < 0
            cond2 = timestamp.minute != self.__lasttimestamp.minute
            if cond1 and cond2:
                isnew = True
                self.__tradeprices = []

        self.__tradeprices.append(float(csvRowDict["price"]))

        open = self.__tradeprices[0]
        high = max(self.__tradeprices)
        low = min(self.__tradeprices)
        close = self.__tradeprices[-1]
        self.__lasttimestamp = timestamp

        # if self.__prevClose is not None:
        #     open = self.__prevClose
        # else:
        #     open = close
        # volume = float(csvRowDict["quantity"])
        # high = max(close, open)
        # low = min(close, open)
        thisbar = bar.BasicBar(timestamp, open, high, low, close, volume, close, None)
        # self.__prevClose = close

        return thisbar, isnew

        # if timezone is None:
        #     timezone = self.__timezone
        #
        # rowParser = GenericRowParser(
        #     self.__columnNames, self.__dateTimeFormat, self.getDailyBarTime(), self.getFrequency(),
        #     timezone, self.__barClass
        # )
        #
        # super(GenericBarFeed, self).addBarsFromCSV(instrument, path, rowParser)
        #
        # if rowParser.barsHaveAdjClose():
        #     self.__haveAdjClose = True
        # elif self.__haveAdjClose:
        #     raise Exception("Previous bars had adjusted close and these ones don't have.")


class Feed(csvfeed.BarFeed):
    def __init__(self):
        csvfeed.BarFeed.__init__(self, barfeed.Frequency.TRADE, maxLen=dataseries.DEFAULT_MAX_LEN)

    def barsHaveAdjClose(self):
        return False

    def addBarsFromCSV(self, instrument, path, m, bar_period):
        rowParser = RowParser()
        # k = 0
        loadedBars = []
        reader = csvutils.FastDictReader(open(path, "r"), fieldnames=rowParser.getFieldNames(),
                                         delimiter=rowParser.getDelimiter())
        # for row in reader:
        #     k = k + 1
        #     if k % m == 0:
        #         bar_ = rowParser.parseBar(row, bar_period)
        #         if bar_ is not None:
        #             loadedBars.append(bar_)
        #     else:
        #         pass
        for row in reader:
            bar_, isnew = rowParser.parseBar(row, bar_period)
            # if not isnew:
                # loadedBars.pop()

            loadedBars.append(bar_)

        self.addBarsFromSequence(instrument, loadedBars)
        super(Feed, self).addBarsFromCSV(instrument, path, rowParser)


class SMACrossOver(strategy.BacktestingStrategy):
    def __init__(self, feed, instrument, smaPeriod):
        super(SMACrossOver, self).__init__(feed)
        self.__instrument = instrument
        self.__longposition = None
        self.__shortposition = None
        # We'll use adjusted close values instead of regular close values.
        # self.setUseAdjustedValues(False)
        self.__prices = feed[instrument].getPriceDataSeries()
        self.__sma = ma.SMA(self.__prices, smaPeriod)
        self.__execInfo = "0,0"

    def getSMA(self):
        return self.__sma

    def onEnterCanceled(self, position):
        if self.__longposition == position:
            self.__longposition = None
        elif self.__shortposition == position:
            self.__shortposition = None
        else:
            assert False

    def onExitOk(self, position):
        if self.__longposition == position:
            self.__longposition = None
            self.__execInfo = str(position.getExitOrder().getAvgFillPrice()) + "," + str(self.__sma[-1]) + ", LX\n"
            self.info(self.__execInfo)
        elif self.__shortposition == position:
            self.__shortposition = None
            self.__execInfo = str(position.getExitOrder().getAvgFillPrice()) + "," + str(self.__sma[-1]) + ", SX\n"
            self.info(self.__execInfo)
        else:
            assert False


    def onExitCanceled(self, position):
        # If the exit was canceled, re-submit it.
        if self.__longposition == position:
            self.__longposition.exitMarket()
        elif self.__shortposition == position:
            self.__shortposition.exitMarket()
        else:
            assert False

    def onEnterOk(self, position):
        # self.__execInfo = position.getEntryOrder().getExecutionInfo()
        if position.getEntryOrder().isBuy():
            side = "LE"
        else:
            side = "SE"

        self.__execInfo = str(position.getEntryOrder().getAvgFillPrice()) + "," +str(self.__sma[-1])+", "+ side + " " \
                          + str(position.getEntryOrder().getFilled())  # , "***", position.getEntryOrder().getId()
        # self.info(position.getEntryOrder())
        self.info(self.__execInfo)
        # self.info(position.getEntryOrder().getExecutionInfo())

    def enterLongSignal(self):
        cond = self.__prices[-1] < (self.__sma[-1] * .995)
        return cond

    def enterShortSignal(self):
        cond = self.__prices[-1] > (self.__sma[-1] * 1.005)
        return cond

    def onBars(self, bars):
        self.info(bars[self.__instrument].getDateTime())
        # If a position was not opened, check if we should enter a long position.
        if self.__sma[-1] is None:
            return

        if self.__longposition is None:
            if self.enterLongSignal():
                shares = int(.5 * self.getBroker().getCash() / bars[self.__instrument].getPrice())
                self.__longposition = self.enterLong(self.__instrument, shares, True)
        elif not self.__longposition.exitActive() and cross.cross_above(self.__prices, self.__sma):
            self.__longposition.exitMarket()

        if self.__shortposition is None:
            if self.enterShortSignal():
                shares = int(.5 * self.getBroker().getCash() / bars[self.__instrument].getPrice())
                self.__shortposition = self.enterShort(self.__instrument, shares, True)
        elif not self.__shortposition.exitActive() and cross.cross_below(self.__prices, self.__sma):
            self.__shortposition.exitMarket()

        recent_bar = bars[self.__instrument]

        info = str(recent_bar.getOpen()) + "-" + str(recent_bar.getHigh()) + "-" + str(recent_bar.getLow()) + "-" \
               + str(recent_bar.getClose()) + "-" + str(self.__sma[-1])
        self.info(info)


def runAllStrat(m, k):
    instrument = "garan"
    barperiod = 1
    feed = Feed()
    feed.addBarsFromCSV(instrument, "gran.csv", m, barperiod)
    strat = SMACrossOver(feed, instrument, k)
    strat.getBroker().setCommission(backtesting.TradePercentage(0.0003))

    tradesAnalyzer = trades.Trades()

    b=feed.getLastBar(instrument)
    strat.attachAnalyzer(tradesAnalyzer)
    strat.run()
    print "# of trades:%i\n" % (tradesAnalyzer.getCount())

    print "%i,%i....Final portfolio value: $%.2f:" % (m, k, strat.getBroker().getEquity())
    return strat.getBroker().getEquity()


def main():
    nticks = range(5, 100 + 1, 1)
    nsma = range(100, 500 + 1, 5)
    # data = Parallel(n_jobs=16)(delayed(runAllStrat)(m=i, k=j) for i in nticks for j in nsma)
    data = Parallel(n_jobs=1)(delayed(runAllStrat)(m=i, k=j) for i in range(1, 2, 1) for j in range(100, 101, 1))

    data = np.matrix(data)
    nrow = len(nticks)
    ncol = len(nsma)
    data = np.resize(data,(nrow,ncol))
    data = pd.DataFrame(data)
    # data.columns=nticks
    # data.index=nsma
    # data.to_csv("outJunl.csv",index_label = 'n_ticks|n_ma')

#    with open('outJunk.csv', 'w') as out:
#       writer = csv.writer(out)
#      writer.writerow(data)


if __name__ == "__main__":
    main()
