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
from pyalgotrade.stratanalyzer import trades
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
        self.__resampledBF = self.resampleBarFeed(bar.Frequency.MONTH, self.onResampledBars)
        self.__resampled_price = self.__resampledBF.getDataSeries()
        self.__resampled_bars = self.__resampledBF.getDataSeries().getCloseDataSeries()
        self.__min_ha = ha.HADir(self.__resampled_price, min_compare_bars)
        self.__max_ha = ha.HADir(self.__resampled_price, max_compare_bars)
        self.__merged_dir = []
        self.__sma = ma.SMA(self.__prices.getPriceDataSeries(), 14)
        self._longposition = None
        self._shortposition = None
        self.__position = None
        self.__State = 0
        self.__criteria = None
        self.__t = None
        # self.getBroker().setAllowNegativeCash(True)
        self.__execInfo = "0,0"
        self.__price = 0
        self.__price_old = 0
        self.__takeProfitOrder = None
        self._stopLossOrder = None
        self.__higestPrice = None
        self.__lowestPrice = None

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
            self.__execInfo = str(position.getExitOrder().getAvgFillPrice()) + ", LX\n"
            self.info(self.__execInfo)
        elif self._shortposition == position:
            self._shortposition = None
            self._stopLossOrder = None
            self.__execInfo = str(position.getExitOrder().getAvgFillPrice()) + ", SX\n"
            self.info(self.__execInfo)
        # else:
        #     assert False


    # def onExitCanceled(self, position):
    #     # If the exit was canceled, re-submit it.
    #     if self._longposition == position:
    #         self._longposition.exitMarket()
    #     elif self._shortposition == position:
    #         self._shortposition.exitMarket()
    #     else:
    #         assert False

    def onEnterOk(self, position):
        # self.__execInfo = position.getEntryOrder().getExecutionInfo()
        if position.getEntryOrder().isBuy():
            side = "LE"
        else:
            side = "SE"

        self.__execInfo = str(position.getEntryOrder().getAvgFillPrice()) + "," + side + " " + str(position.getEntryOrder().getFilled())\
        #                   + str(position.getEntryOrder().getFilled())  # , "***", position.getEntryOrder().getId()
        #self.info(position.getEntryOrder())
        self.info(self.__execInfo)
        # self.info(position.getEntryOrder().getExecutionInfo())

    def enterLongSignal(self):
        cond = self.__min_ha[-1][0] == 1 and self.__max_ha[-1][0] == 1
        cond = self.__merged_dir[-1] == 1 and not self.__max_ha[-1][0] is None
        return cond

    def enterShortSignal(self):
        cond = self.__min_ha[-1][0] == -1 and self.__max_ha[-1][0] == -1
        cond = self.__merged_dir[-1] == -1 and not self.__max_ha[-1][0] is None
        return cond

    def onOrderUpdated(self, order):
        if order.isFilled() and order.getAction() == 1:
            # Was the take profit order filled ?
            if self.__takeProfitOrder is not None and order.getId() == self.__takeProfitOrder.getId():
                entryPrice = order.getExecutionInfo().getPrice()
                print self.getFeed().getCurrentBars().getDateTime(), "Take profit order filled at", entryPrice
                # self.__takeProfitOrder = None
                # Cancel the other exit order to avoid entering a short position.
                self.getBroker().cancelOrder(self.__stopLossOrder)
            # Was the stop loss order filled ?
            elif order.getId() == 75:
                print 'DEBUG'
            elif self._stopLossOrder is not None and order.getId() == self._stopLossOrder.getId():
                entryPrice = order.getExecutionInfo().getPrice()
                print self.getFeed().getCurrentBars().getDateTime(), "Stop loss order filled at", entryPrice
                self._stopLossOrder = None
                # Cancel the other exit order to avoid entering a short position.
                # self.getBroker().cancelOrder(self.__takeProfitOrder)
            else: # It is the buy order that got filled.
                entryPrice = order.getExecutionInfo().getPrice()
                self.__higestPrice = entryPrice
                shares = order.getExecutionInfo().getQuantity()
                self.info("Buy order filled at " + "%.2f" % entryPrice)
                # Submit take-profit and stop-loss orders.
                # In the next version I'll provide a shortcut for this similar to self.order(...) for market orders.
                # takeProfitPrice = entryPrice * 1.01
                # self.__takeProfitOrder = self.getBroker().createLimitOrder(broker.Order.Action.SELL, self.__instrument, takeProfitPrice, shares)
                # self.__takeProfitOrder.setGoodTillCanceled(True)
                # self.getBroker().submitOrder(self.__takeProfitOrder)
                newPrice = self.__price
                # highestprice = entryprice
                # if newPrice > highestprice
                #     highestprice = newprice
                # stoplossPrice = 0.95 * highestprice
                stopLossPrice = self.__higestPrice * 0.95
                self._stopLossOrder = self.getBroker().createStopOrder(broker.Order.Action.SELL, self.__instrument, stopLossPrice, shares)
                self._stopLossOrder.setGoodTillCanceled(True)
                self.getBroker().submitOrder(self._stopLossOrder)
                # print "Take-profit set at", takeProfitPrice
                self.info("trailing stop price set at " + "%.2f" % stopLossPrice)

        elif order.isFilled() and order.getType() == 1 and order.getAction() == 3:
            self.info('MARKET EXIT')
            self.__higestPrice = None
            if self._stopLossOrder is not None and self._stopLossOrder.isActive():
                self.getBroker().cancelOrder(self._stopLossOrder)
                self._stopLossOrder = None

        elif order.isFilled() and order.getType() == 3:
            self.info('STOP EXIT ' + '%.2f' % order.getAvgFillPrice())
            self._longposition = None

    def onResampledBars(self, dt, bars):
        bar = bars[self.__instrument]
        self.info('RESAMPLED ' + str(bar.getDateTime()) +' ' + '%.2f' % bar.getClose())

    def onBars(self, bars):
        self.info('%.2f' % bars[self.__instrument].getClose())
        if self.__min_ha and self.__max_ha:
            if self.__min_ha[-1][0] is None and self.__max_ha[-1][0] is None:
                return
            else:
                pass
                # print self.__min_ha[-1][0], self.__max_ha[-1][0]
        # trailing_stop = 0.05
        # bar = bars[self.__instrument]
        # barG = bars[self.__genki]
        #
        # if self.__min_ha[-1][0] is None and self.__max_ha[-1][0] is None:
        #     return
        # elif self.__max_ha[-1][0] is None:
        #     self.__merged_dir.append(self.__min_ha[-1][0])
        # else:
        #     comb_index = self.__max_ha[-1][1]
        #     if comb_index == 0:
        #         self.__merged_dir.append(self.__max_ha[-1][0])
        #     else:
        #         combDir = self.__merged_dir[-comb_index]
        #         if combDir == self.__max_ha[-1][0]:
        #             self.__merged_dir.append(self.__max_ha[-1][0])
        #         else:
        #             self.__merged_dir.append(0)

        # state = 0
        # if self.enterLongSignal():
        #     state = 1
        # elif self.enterShortSignal():
        #     state = -1
        #
        # self.__price = bars[self.__instrument].getPrice()
        # # price change i max ve min fiyat bazli hesapla
        # price_change = self.__price - self.__price_old
        # self.__price_old = self.__price
        # # shares = int(50000 / self.__price)
        # shares = 500
        #
        # myshares = self.getBroker().getShares(self.__instrument)
        #
        # self.info((str(barG.getDateTime()) + ', ' + "%.2f" % barG.getOpen() + ', ' + "%.2f" % barG.getClose() +
        #            ', ' + str(state) + ',' + str(self.__merged_dir[-1]) + ', ' + str(self.__min_ha[-1]) +
        #            str(self.__max_ha[-1]) + "%.2f" % bar.getOpen() + ' ' + "%.2f" % bar.getClose())
        #           + ' ' + "%.2f" % price_change + ' ' + str(myshares))
        #
        #
        # order = self.getBroker().getActiveOrders()
        # # self.info(str(len(order)))
        # if order:
        #     order = order[0]
        #     # print 'debug'
        #     if not order.isFilled() and order.getType() == 3 and order.isActive():
        #         stopLossOrder = order
        #         if bar.getHigh() > self.__higestPrice:
        #             shares = order.getQuantity()
        #             self.getBroker().cancelOrder(order)
        #
        #             self.__higestPrice = self.__price
        #             stopLossPrice = self.__higestPrice * 0.95
        #             self.info('update trailing stop price at ' + "%.2f" % stopLossPrice)
        #
        #             self._stopLossOrder = self.getBroker().createStopOrder(broker.Order.Action.SELL, self.__instrument,
        #                                                                    stopLossPrice, shares)
        #             self._stopLossOrder.setGoodTillCanceled(True)
        #             self.getBroker().submitOrder(self._stopLossOrder)
        #         else:
        #             self.info('no need to update trailing stop price')
        #
        # if self._longposition is None and self._shortposition is None:
        #     if self.enterLongSignal():
        #         self.info(bar.getDateTime())
        #         self._longposition = self.enterLong(self.__instrument, shares, True)
        #     elif self.enterShortSignal():
        #         self.info(bar.getDateTime())
        #         # self._shortposition = self.enterShort(self.__instrument, shares, True)
        #
        # elif self._longposition is None and self._shortposition is not None:
        #     if self.enterLongSignal():
        #         self.info(bar.getDateTime())
        #         if not self._shortposition.exitActive() and self._shortposition.getShares() != 0:
        #             self._shortposition.exitMarket()
        #         self._longposition = self.enterLong(self.__instrument, shares, True)
        #     # else:
        #     #     # trailing stop part for short positions
        #     #     if not self._shortposition.exitActive() and price_change < 0:
        #     #         if self.__stopLossOrder is not None:
        #     #             # entryPrice = order.getExecutionInfo().getPrice()
        #     #             print self.getFeed().getCurrentBars().getDateTime(), "Stop loss order filled at", entryPrice
        #     #             self.__stopLossOrder = None
        #     #             # Cancel the other exit order to avoid entering a short position.
        #     #             self.getBroker().cancelOrder(self.__takeProfitOrder)
        #     #
        #     #         shares = self._shortposition.getEntryOrder().getQuantity()
        #     #         self.__stopLossOrder = self.getBroker().createStopOrder(broker.Order.Action.BUY_TO_COVER,
        #     #                                                                 self.__instrument, (1 + trailing_stop),
        #     #                                                                 shares)
        #     #         self.__stopLossOrder.setGoodTillCanceled(True)
        #     #         self.getBroker().submitOrder(self.__stopLossOrder)
        #
        # elif self._shortposition is None and self._longposition is not None:
        #     if self.enterShortSignal():
        #         self.info(bar.getDateTime())
        #         if not self._longposition.exitActive() and self._longposition.getShares() != 0:
        #             self.info('Signal Exit')
        #             self.getBroker().cancelOrder(self._stopLossOrder)
        #             self._longposition.exitMarket()
        #         # self._shortposition = self.enterShort(self.__instrument, shares, True)
        #     # else:
        #     #     # trailing stop part for long positions
        #     #     if not self._longposition.exitActive() and price_change > 0:
        #     #         active_orders = self.getBroker().getActiveOrders()
        #     #         if active_orders:
        #     #             self.getBroker().cancelOrder(active_orders[-1])
        #     #         self._longposition = self._longposition.exitStop((1 - trailing_stop) * self.__price, True)




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

    tradesAnalyzer = trades.Trades()
    strat.attachAnalyzer(tradesAnalyzer)

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
    print tradesAnalyzer.getCount()

    if plot:
        plt.plot()


if __name__ == "__main__":
    main(True)
