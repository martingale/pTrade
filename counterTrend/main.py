from pyalgotrade import strategy
from pyalgotrade import plotter
from pyalgotrade.barfeed import csvfeed
from pyalgotrade.technical import bollinger

from pyalgotrade.stratanalyzer import returns as rets
from pyalgotrade.stratanalyzer import drawdown
from pyalgotrade.stratanalyzer import sharpe
from pyalgotrade.stratanalyzer import trades

from pyalgotrade import bar
from pyalgotrade.technical import cross
import datetime

import time


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
        bar_time = csvRowDict["Time"]
        secs = (int(bar_time[:-3]) * 60 + int(bar_time[-2:])) * 60

        dateTime = bar_date + datetime.timedelta(seconds=secs)
        if dateTime.minute == 59:
            dateTime = dateTime + datetime.timedelta(seconds=60)

        open_price = float(csvRowDict["Open"])
        high_price = float(csvRowDict["High"])
        low_price = float(csvRowDict["Low"])
        close_price = float(csvRowDict["Close"])

        try:
            volume = float(csvRowDict["Vol"])
        except KeyError:
            volume = 1000000
            
        bar_ = bar.BasicBar(dateTime, open_price, high_price, low_price, close_price, volume, close_price, None)

        return bar_


class Bars(csvfeed.BarFeed):
    def __init__(self, frequency=bar.Frequency.DAY, maxLen=1024):
        super(Bars, self).__init__(frequency, maxLen)

    def barsHaveAdjClose(self):
        return False

    def addBarsFromCSV(self, instrument, path, row_parser):
        rowParser = RowParser()
        super(Bars, self).addBarsFromCSV(instrument, path, rowParser)


class BBands(strategy.BacktestingStrategy):
    def __init__(self, feed, instrument, bBandsPeriod_upper, bBandsPeriod_lower):
        super(BBands, self).__init__(feed)
        # strategy.BacktestingStrategy.__init__(self, feed)
        self.__instrument = instrument
        self.__prices = feed[instrument].getCloseDataSeries()
        self.__bbands = bollinger.BollingerBands(self.__prices, bBandsPeriod_upper, 3)
        self.__bbands_upper = bollinger.BollingerBands(self.__prices, bBandsPeriod_upper, 3)
        self.__bbands_lower = bollinger.BollingerBands(self.__prices, bBandsPeriod_lower, 3)
        self.__positionLong = None
        self.__positionShort = None
        self.__position = None
        self.__State = 0
        self.__t = None
        self.getBroker().setAllowNegativeCash(False)
        self.counter = 0

    @property
    def getBollingerBands_upper(self):
        return self.__bbands_upper
    @property
    def getBollingerBands_lower(self):
        return self.__bbands_lower

    def onEnterCanceled(self, position):
        if self.__positionLong == position:
            self.__positionLong = None
        elif self.__positionShort == position:
            self.__positionShort = None
        else:
            assert False

    def onExitOk(self, position):
        if self.__positionLong == position:
            self.__positionLong = None
            self._stopLossOrder = None
            self.__execInfo = str(position.getExitOrder().getAvgFillPrice()) + ", LX"
        elif self.__positionShort == position:
            self.__positionShort = None
            self._stopLossOrder = None
            self.__execInfo = str(position.getExitOrder().getAvgFillPrice()) + ", SX"

        self.info(self.__execInfo)


    def onEnterOk(self, position):
        if position.getEntryOrder().isBuy():
            exec_info = str(position.getEntryOrder().getAvgFillPrice()) + ", LE"
        else:
            exec_info = str(position.getEntryOrder().getAvgFillPrice()) + ", SE"

        self.info(exec_info)

    def onBars(self, bars):
        bar = bars[self.__instrument]
        self.counter += 1

        lower = self.__bbands_lower.getLowerBand()[-1]
        upper = self.__bbands_upper.getUpperBand()[-1]

        # self.info(str(self.counter) + ' ' + str(bars.getDateTime()) + ' ' + '%.3f' % bar.getClose())

        if upper is None or lower is None:
            return

        baseshare = 100

        upper = self.__bbands.getUpperBand()[-1]
        lower = self.__bbands.getLowerBand()[-1]
        mid = self.__bbands.getMiddleBand()[-1]

        # self.info(str(self.counter) + ' ' + str(bars.getDateTime()) + ' ' + '%.3f' % bar.getClose() + ' ' +
        #           '%.3f' % upper + ' ' + '%.3f' % lower + ' ' + '%.3f' % mid)

        if cross.cross_above(self.__prices, self.__bbands_lower.getLowerBand()):
            if self.__positionShort is not None and not self.__positionShort.exitActive():
                self.__positionShort.exitMarket()
            if self.__positionLong is None:
                self.__positionLong = self.enterLongStop(self.__instrument, lower, baseshare)
        elif cross.cross_below(self.__prices, self.__bbands_upper.getUpperBand()):
            if self.__positionLong is not None and not self.__positionLong.exitActive():
                self.__positionLong.exitMarket()
            if self.__positionShort is None:
                self.__positionShort = self.enterShortStop(self.__instrument, upper, baseshare)

def main(plot):
    instrument = "USDJPY"

    path = 'USDJPY_60min_32mo_010418_data+BBands.txt'

    feed = Bars()
    feed.addBarsFromCSV(instrument, path, RowParser)

    bBandsPeriod_upper = 80
    bBandsPeriod_lower = 80

    strat = BBands(feed, instrument, bBandsPeriod_upper, bBandsPeriod_lower)
    # sharpeRatioAnalyzer = sharpe.SharpeRatio()
    # strat.attachAnalyzer(sharpeRatioAnalyzer)
    #
    # tradesAnalyzer = trades.Trades()
    # strat.attachAnalyzer(tradesAnalyzer)

    retAnalyzer = rets.Returns()
    strat.attachAnalyzer(retAnalyzer)
    sharpeRatioAnalyzer = sharpe.SharpeRatio()
    strat.attachAnalyzer(sharpeRatioAnalyzer)
    drawDownAnalyzer = drawdown.DrawDown()
    strat.attachAnalyzer(drawDownAnalyzer)
    tradesAnalyzer = trades.Trades()
    strat.attachAnalyzer(tradesAnalyzer)

    if plot:
        plt = plotter.StrategyPlotter(strat, True, True, True)
        plt.getInstrumentSubplot(instrument).addDataSeries("upper", strat.getBollingerBands_upper.getUpperBand())
        # plt.getInstrumentSubplot(instrument).addDataSeries("middle", strat.getBollingerBands().getMiddleBand())
        plt.getInstrumentSubplot(instrument).addDataSeries("lower", strat.getBollingerBands_lower.getLowerBand())
    start_time = time.time()  # taking current time as starting time
    strat.run()
    elapsed_time = time.time() - start_time
    print("Time elapsed: %.4f seconds" % elapsed_time)

    print "Final portfolio value: $%.2f" % strat.getResult()
    print "Cumulative returns: %.2f %%" % (retAnalyzer.getCumulativeReturns()[-1] * 100)
    print "Sharpe ratio: %.2f" % (sharpeRatioAnalyzer.getSharpeRatio(0.05))
    print "Max. drawdown: %.2f %%" % (drawDownAnalyzer.getMaxDrawDown() * 100)
    print "Longest drawdown duration: %s" % (drawDownAnalyzer.getLongestDrawDownDuration())

    print
    print "Total trades: %d" % (tradesAnalyzer.getCount())
    if tradesAnalyzer.getCount() > 0:
        profits = tradesAnalyzer.getAll()
        print "Avg. profit: $%2.f" % (profits.mean())
        print "Profits std. dev.: $%2.f" % (profits.std())
        print "Max. profit: $%2.f" % (profits.max())
        print "Min. profit: $%2.f" % (profits.min())
        returns = tradesAnalyzer.getAllReturns()
        print "Avg. return: %2.f %%" % (returns.mean() * 100)
        print "Returns std. dev.: %2.f %%" % (returns.std() * 100)
        print "Max. return: %2.f %%" % (returns.max() * 100)
        print "Min. return: %2.f %%" % (returns.min() * 100)

    print
    print "Profitable trades: %d" % (tradesAnalyzer.getProfitableCount())
    if tradesAnalyzer.getProfitableCount() > 0:
        profits = tradesAnalyzer.getProfits()
        print "Avg. profit: $%2.f" % (profits.mean())
        print "Profits std. dev.: $%2.f" % (profits.std())
        print "Max. profit: $%2.f" % (profits.max())
        print "Min. profit: $%2.f" % (profits.min())
        returns = tradesAnalyzer.getPositiveReturns()
        print "Avg. return: %2.f %%" % (returns.mean() * 100)
        print "Returns std. dev.: %2.f %%" % (returns.std() * 100)
        print "Max. return: %2.f %%" % (returns.max() * 100)
        print "Min. return: %2.f %%" % (returns.min() * 100)

    print
    print "Unprofitable trades: %d" % (tradesAnalyzer.getUnprofitableCount())
    if tradesAnalyzer.getUnprofitableCount() > 0:
        losses = tradesAnalyzer.getLosses()
        print "Avg. loss: $%2.f" % (losses.mean())
        print "Losses std. dev.: $%2.f" % (losses.std())
        print "Max. loss: $%2.f" % (losses.min())
        print "Min. loss: $%2.f" % (losses.max())
        returns = tradesAnalyzer.getNegativeReturns()
        print "Avg. return: %2.f %%" % (returns.mean() * 100)
        print "Returns std. dev.: %2.f %%" % (returns.std() * 100)
        print "Max. return: %2.f %%" % (returns.max() * 100)
        print "Min. return: %2.f %%" % (returns.min() * 100)

    if plot:
        plt.plot()


if __name__ == "__main__":
    main(True)
