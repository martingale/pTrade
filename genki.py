from pyalgotrade import strategy
from pyalgotrade import plotter
from pyalgotrade import dataseries
from pyalgotrade import technical
from pyalgotrade.barfeed import csvfeed
from pyalgotrade.technical import bollinger
from pyalgotrade.technical import ma
from pyalgotrade.stratanalyzer import sharpe
from pyalgotrade import bar
from pyalgotrade import barfeed
from pyalgotrade.barfeed import csvfeed
from pyalgotrade import broker
from pyalgotrade.technical import cross
from pyalgotrade.utils import csvutils
import datetime
import time
import HA as ha


class RowParserHA(csvfeed.RowParser):
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
        bar_date = datetime.datetime.strptime(csvRowDict["Date"], "%d.%m.%Y") #05/06/1998,00:00
        bar_time = datetime.datetime.strptime(csvRowDict["Time"], "%H:%M") #05/06/1998,00:00

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

        return bar_, ha_bar


class GenkiBars(csvfeed.BarFeed):
    def __init__(self):
        csvfeed.BarFeed.__init__(self, barfeed.Frequency.TRADE, maxLen=dataseries.DEFAULT_MAX_LEN)

    def barsHaveAdjClose(self):
        return False

    def addBarsFromCSV(self, instrument, path, row_parser):
        row_parser = RowParserHA()
        loaded_genki = []
        loaded_bars = []
        reader = csvutils.FastDictReader(open(path, "r"), fieldnames=row_parser.getFieldNames(),
                                         delimiter=row_parser.getDelimiter())
        for row in reader:
            bar_, bar_genki = row_parser.parseBar(row)
            if bar_genki is not None and bar_ is not None:
                loaded_genki.append(bar_genki)
                loaded_bars.append(bar_)
            else:
                pass

        self.addBarsFromSequence(instrument, loaded_bars)
        self.addBarsFromSequence(instrument+'genki', loaded_genki)


class GenkiStrategy(strategy.BacktestingStrategy):
    def __init__(self, feed, instrument, min_compare_bars=1, max_compare_bars=6):
        super(GenkiStrategy, self).__init__(feed)
        self.__instrument = instrument
        self.__genki = instrument + 'genki'
        self.__prices = feed[instrument]
        self.__ha = feed[self.__genki]
        self.__min_ha = ha.HADir(self.__ha, min_compare_bars)
        self.__max_ha = ha.HADir(self.__ha, max_compare_bars)
        self.__sma = ma.SMA(feed[instrument].getPriceDataSeries(), 14)
        self.__longposition = None
        self.__shortposition = None
        self.__position = None
        self.__State = 0
        self.__criteria = None
        self.__t = None
        # self.getBroker().setAllowNegativeCash(True)
        self.__execInfo = "0,0"

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
            self.__execInfo = str(position.getExitOrder().getAvgFillPrice()) + ", LX\n"
            self.info(self.__execInfo)
        elif self.__shortposition == position:
            self.__shortposition = None
            self.__execInfo = str(position.getExitOrder().getAvgFillPrice()) + ", SX\n"
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

        self.__execInfo = str(position.getEntryOrder().getAvgFillPrice()) + "," + side + " " \
        #                   + str(position.getEntryOrder().getFilled())  # , "***", position.getEntryOrder().getId()
        #self.info(position.getEntryOrder())
        self.info(self.__execInfo)
        # self.info(position.getEntryOrder().getExecutionInfo())

    def enterLongSignal(self):
        cond = self.__min_ha[-1][0] == 1 and self.__max_ha[-1][0] == 1
        return cond

    def enterShortSignal(self):
        cond = self.__min_ha[-1][0] == -1 and self.__max_ha[-1][0] == -1
        return cond

    def onBars(self, bars):
        # bar = bars[self.__instrument]
        barG = bars[self.__genki]

        if self.__min_ha[-1][0] is None or self.__max_ha[-1][0] is None:
            return

        state = 0
        if self.enterLongSignal():
            state = 1
        elif self.enterShortSignal():
            state = -1

        self.info((str(barG.getDateTime()) + ', ' + "%.2f" % barG.getOpen() + ', ' + "%.2f" % barG.getClose() +
                   ', ' + str(state) + ', ' + str(self.__min_ha[-1]) + str(self.__max_ha[-1])))
        # self.info((str(barG.getDateTime()) + ', ' + str(self.__min_ha[-1]) + str(self.__max_ha[-1])))

        shares = int(50000 / bars[self.__instrument].getPrice())
        if self.__longposition is None and self.__shortposition is None:
            if self.enterLongSignal():
                self.__longposition = self.enterLong(self.__instrument, shares, True)
            elif self.enterShortSignal():
                self.__shortposition = self.enterShort(self.__instrument, shares, True)
        elif self.__longposition is None:
            if self.enterLongSignal():
                if not self.__shortposition.exitActive():
                    self.__shortposition.exitMarket()
                self.__longposition = self.enterLong(self.__instrument, shares, True)
        elif self.__shortposition is None:
            if self.enterShortSignal():
                if not self.__longposition.exitActive():
                    self.__longposition.exitMarket()
                self.__shortposition = self.enterShort(self.__instrument, shares, True)


def main(plot):
    instrument = "eurusd"
    min_compare_bars = 1
    max_compare_bars = 10

    # Download the bars.
    genki_bars = GenkiBars()
    # feed= csvfeed.GenericBarFeed(bar.Frequency.HOUR)
    # feed1.setDateTimeFormat("%Y-%m-%d %H:%M:%S")
    genki_bars.addBarsFromCSV(instrument, "SPY_daily_new.txt", RowParserHA)

    strat = GenkiStrategy(genki_bars, instrument, min_compare_bars, max_compare_bars)
    sharpeRatioAnalyzer = sharpe.SharpeRatio()
    strat.attachAnalyzer(sharpeRatioAnalyzer)

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

    if plot:
        plt.plot()


if __name__ == "__main__":
    main(True)
