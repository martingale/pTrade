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
import copy as cp
from pyalgotrade.utils.collections import ListDeque
from pandas.tseries.offsets import BMonthEnd
import numpy as np

class fixedLenList(list):
    def __init__(self, length):
        super(fixedLenList, self).__init__()
        self.length = length
        self.values = []

    def append(self, value):
        self.values.append(value)
        if len(self.values) >= self.length:
            self.values.pop()

    def isFull(self):
        return len(self.values) == self.length



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
        bar_date = datetime.datetime.strptime(csvRowDict["Date"], "%m/%d/%Y") #- datetime.timedelta(days=1) #05/06/1998,00:00
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

        # return bar_, ha_bar
        return bar_

class GenkiBars(csvfeed.BarFeed):
    def __init__(self):
        csvfeed.BarFeed.__init__(self, barfeed.Frequency.TRADE, maxLen=dataseries.DEFAULT_MAX_LEN)

    def barsHaveAdjClose(self):
        return False

    def addBarsFromCSV(self, instrument, path, row_parser):
        row_parser = RowParserHA()
        # loaded_genki = []
        loaded_bars = []
        reader = csvutils.FastDictReader(open(path, "r"), fieldnames=row_parser.getFieldNames(),
                                         delimiter=row_parser.getDelimiter())
        for row in reader:
            # bar_, bar_genki = row_parser.parseBar(row)
            bar_ = row_parser.parseBar(row)
            # if bar_genki is not None and bar_ is not None:
            if bar_ is not None:
                # loaded_genki.append(bar_genki)
                loaded_bars.append(bar_)
            else:
                pass

        self.addBarsFromSequence(instrument, loaded_bars)
        # self.addBarsFromSequence(instrument+'genki', loaded_genki)


class GenkiStrategy(strategy.BacktestingStrategy):
    def __init__(self, feed, instrument, min_compare_bars=1, max_compare_bars=6):
        super(GenkiStrategy, self).__init__(feed)
        self.__instrument = instrument
        self.__min_compare_bars = min_compare_bars
        self.__max_compare_bars = max_compare_bars
        # self.__genki = instrument + 'genki'
        self.prices = feed[instrument]
        self.resampledBF = self.resampleBarFeed(bar.Frequency.MONTH, self.onResampledBars)
        self.resampled_price = self.resampledBF.getDataSeries()

        # self.temp_bar = barfeed.BaseBarFeed(bar.Frequency.DAY)

        # self.temp_ha_min = ha.HADir(self.resampled_price, max_compare_bars)
        self.resampled_bars = self.resampledBF.getDataSeries().getCloseDataSeries().getValues()
        self.resampledClose = self.resampledBF.getDataSeries().getCloseDataSeries()
        self.ha_bar = ha.HADir(self.resampled_price)
        # self.max_ha = ha.HADir(self.resampled_price, max_compare_bars)
        self.__merged_dir = []
        # self.__sma = ma.SMA(self.prices.getPriceDataSeries(), 14)
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

        self.__daily_bar = None
        self.__ha_bars = fixedLenList(self.__max_compare_bars)


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

    def enterLongSignal(self, x, y):
        cond = x[0] == y[0] == 1
        return cond

    def enterShortSignal(self, x, y):
        cond = x[0] == y[0] == -1
        return cond

    # def onOrderUpdated(self, order):
    #     if order.isFilled() and order.getAction() == 1:
    #         # Was the take profit order filled ?
    #         if self.__takeProfitOrder is not None and order.getId() == self.__takeProfitOrder.getId():
    #             entryPrice = order.getExecutionInfo().getPrice()
    #             print self.getFeed().getCurrentBars().getDateTime(), "Take profit order filled at", entryPrice
    #             # self.__takeProfitOrder = None
    #             # Cancel the other exit order to avoid entering a short position.
    #             self.getBroker().cancelOrder(self.__stopLossOrder)
    #         # Was the stop loss order filled ?
    #         elif order.getId() == 75:
    #             print 'DEBUG'
    #         elif self._stopLossOrder is not None and order.getId() == self._stopLossOrder.getId():
    #             entryPrice = order.getExecutionInfo().getPrice()
    #             print self.getFeed().getCurrentBars().getDateTime(), "Stop loss order filled at", entryPrice
    #             self._stopLossOrder = None
    #             # Cancel the other exit order to avoid entering a short position.
    #             # self.getBroker().cancelOrder(self.__takeProfitOrder)
    #         else: # It is the buy order that got filled.
    #             entryPrice = order.getExecutionInfo().getPrice()
    #             self.__higestPrice = entryPrice
    #             shares = order.getExecutionInfo().getQuantity()
    #             self.info("Buy order filled at " + "%.2f" % entryPrice)
    #             # Submit take-profit and stop-loss orders.
    #             # In the next version I'll provide a shortcut for this similar to self.order(...) for market orders.
    #             # takeProfitPrice = entryPrice * 1.01
    #             # self.__takeProfitOrder = self.getBroker().createLimitOrder(broker.Order.Action.SELL, self.__instrument, takeProfitPrice, shares)
    #             # self.__takeProfitOrder.setGoodTillCanceled(True)
    #             # self.getBroker().submitOrder(self.__takeProfitOrder)
    #             newPrice = self.__price
    #             # highestprice = entryprice
    #             # if newPrice > highestprice
    #             #     highestprice = newprice
    #             # stoplossPrice = 0.95 * highestprice
    #             stopLossPrice = self.__higestPrice * 0.95
    #             self._stopLossOrder = self.getBroker().createStopOrder(broker.Order.Action.SELL, self.__instrument, stopLossPrice, shares)
    #             self._stopLossOrder.setGoodTillCanceled(True)
    #             self.getBroker().submitOrder(self._stopLossOrder)
    #             # print "Take-profit set at", takeProfitPrice
    #             self.info("trailing stop price set at " + "%.2f" % stopLossPrice)
    #
    #     elif order.isFilled() and order.getType() == 1 and order.getAction() == 3:
    #         self.info('MARKET EXIT')
    #         self.__higestPrice = None
    #         if self._stopLossOrder is not None and self._stopLossOrder.isActive():
    #             self.getBroker().cancelOrder(self._stopLossOrder)
    #             self._stopLossOrder = None
    #
    #     elif order.isFilled() and order.getType() == 3:
    #         self.info('STOP EXIT ' + '%.2f' % order.getAvgFillPrice())
    #         self._longposition = None

    def onBars(self, bars):
        bar = bars[self.__instrument]
        self.__daily_bar = bar

    def mergeMonth(self, date_time):
        if BMonthEnd().rollforward(date_time) != date_time and self.__merged_dir:
            self.__merged_dir.pop()

    def compBars(self, n):
        n += 1
        values = self.ha_bar.getValues().data()
        ha_open = values[-1]['haOpen']
        ha_close = values[-1]['haClose']
        return_val = None
        if n == 1:
            if ha_close >= ha_open:
                return_val = [1, 0]
            else:
                return_val = [-1, 0]
        else:
            for i in range(n - 1, 1, -1):  # farthest bar
                subset_values = values[-i:-(i - 1)]
                open_values = [x['haOpen'] for x in subset_values]
                close_values = [x['haClose'] for x in subset_values]
                all_values = np.append(open_values, close_values)
                max_val = max(all_values)
                min_val = min(all_values)

                if ha_open >= min_val and ha_open <= max_val and ha_close >= min_val and ha_close <= max_val:
                    if close_values[-1] > open_values[-1]:
                        return_val = [1, i-1]
                    else:
                        return_val = [-1, i-1]
                    break
                else:
                    if ha_close > ha_open:
                        return_val = [1, 0]
                    else:
                        return_val = [-1, 0]
        return return_val

    def onResampledBars(self, dt, bars):
        date_time = self.__daily_bar.getDateTime()
        if len(self.ha_bar) >= self.__max_compare_bars + 1:
            min_compbar = self.compBars(self.__min_compare_bars)
            max_compbar = self.compBars(self.__max_compare_bars)
            # self.info('%.2f' % self.ha_bar[-1]['haOpen'] + ' ' +
            #           '%.2f' % self.ha_bar[-1]['haClose'] + ' ' +
            #           str(compbar[0]) + ' ' +
            #           str(compbar[1]))

            trailing_stop = 0.05
            bar = self.__daily_bar
            mybar = bars[self.__instrument]

            longSig = self.enterLongSignal(min_compbar, max_compbar)
            shortSig = self.enterShortSignal(min_compbar, max_compbar)

            state = 0
            if longSig:
                state = 1
            elif shortSig:
                state = -1

            self.__price = bars[self.__instrument].getPrice()
            # price change i max ve min fiyat bazli hesapla
            self.__price_old = self.__price
            # shares = int(50000 / self.__price)
            shares = 10

            # myshares = self.getBroker().getShares(self.__instrument)

            if str(date_time.date()) == '1999-08-24':
                pass

            # if self.min_ha[-1][0] is not None and self.max_ha[-1][0] is not None:
            self.info(str(bar.getDateTime()) + ' [' +
                      '%.2f' % bar.getOpen() + ' ' +
                      '%.2f' % bar.getHigh() + ' ' +
                      '%.2f' % bar.getLow() + ' ' +
                      '%.2f' % bar.getClose() + '] [' +
                      '%.2f' % mybar.getOpen() + ' ' +
                      '%.2f' % mybar.getHigh() + ' ' +
                      '%.2f' % mybar.getLow() + ' ' +
                      '%.2f' % mybar.getClose() + '] ' +
                      '%.2f' % self.ha_bar[-1]['haOpen'] + ' ' +
                      '%.2f' % self.ha_bar[-1]['haClose'] + ' ' +
                      str(min_compbar[0]) + ' ' +
                      str(max_compbar[0]) + ' ' +
                      str(longSig) + ' ' +
                      str(shortSig)
                      )


            # order = self.getBroker().getActiveOrders()
            # self.info(str(len(order)))
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

            if self._longposition is None and self._shortposition is None:
                if longSig:
                    # self.info(bar.getDateTime())
                    self._longposition = self.enterLong(self.__instrument, shares, True)
                elif shortSig:
                    pass
                    # self.info(bar.getDateTime())
                    self._shortposition = self.enterShort(self.__instrument, shares, True)

            elif self._longposition is None and self._shortposition is not None:
                if longSig:
                    if not self._shortposition.exitActive():# and self._shortposition.getShares() != 0:
                        self._shortposition.exitMarket()
                    self._longposition = self.enterLong(self.__instrument, shares, True)
                # else:
                #     # trailing stop part for short positions
                #     if not self._shortposition.exitActive() and price_change < 0:
                #         if self.__stopLossOrder is not None:
                #             # entryPrice = order.getExecutionInfo().getPrice()
                #             print self.getFeed().getCurrentBars().getDateTime(), "Stop loss order filled at", entryPrice
                #             self.__stopLossOrder = None
                #             # Cancel the other exit order to avoid entering a short position.
                #             self.getBroker().cancelOrder(self.__takeProfitOrder)
                #
                #         shares = self._shortposition.getEntryOrder().getQuantity()
                #         self.__stopLossOrder = self.getBroker().createStopOrder(broker.Order.Action.BUY_TO_COVER,
                #                                                                 self.__instrument, (1 + trailing_stop),
                #                                                                 shares)
                #         self.__stopLossOrder.setGoodTillCanceled(True)
                #         self.getBroker().submitOrder(self.__stopLossOrder)

            elif self._shortposition is None and self._longposition is not None:
                if shortSig:
                    if not self._longposition.exitActive():# and self._longposition.getShares() != 0:
                        # self.getBroker().cancelOrder(self._stopLossOrder)
                        self._longposition.exitMarket()
                    self._shortposition = self.enterShort(self.__instrument, shares, True)
                # else:
                #     # trailing stop part for long positions
                #     if not self._longposition.exitActive() and price_change > 0:
                #         active_orders = self.getBroker().getActiveOrders()
                #         if active_orders:
                #             self.getBroker().cancelOrder(active_orders[-1])
                #         self._longposition = self._longposition.exitStop((1 - trailing_stop) * self.__price, True)




def main(plot):
    instrument = "eurusd"
    min_compare_bars = 10
    max_compare_bars = 11

    # Download the bars.
    genki_bars = GenkiBars()
    # feed= csvfeed.GenericBarFeed(bar.Frequency.HOUR)
    # feed1.setDateTimeFormat("%Y-%m-%d %H:%M:%S")
    genki_bars.addBarsFromCSV(instrument, "DOW_daily_OHLC_041188-041218.txt", RowParserHA)

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
    main(False)
