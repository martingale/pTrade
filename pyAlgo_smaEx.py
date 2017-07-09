from pyalgotrade import strategy
from pyalgotrade import plotter
from pyalgotrade.barfeed import csvfeed
from pyalgotrade.technical import bollinger
from pyalgotrade.stratanalyzer import sharpe
from pyalgotrade import bar
from pyalgotrade import broker
from pyalgotrade.technical import cross

import time

class BBands(strategy.BacktestingStrategy):
    def __init__(self, feed, instrument, bBandsPeriod_upper,bBandsPeriod_lower):
        super(BBands, self).__init__(feed)
        # strategy.BacktestingStrategy.__init__(self, feed)
        self.__instrument = instrument
        self.__prices = feed[instrument].getPriceDataSeries()
        self.__bbands_upper = bollinger.BollingerBands(self.__prices, bBandsPeriod_upper, 2.8,2)
        self.__bbands_lower = bollinger.BollingerBands(self.__prices, bBandsPeriod_lower, 3.2,2)
        self.__positionLong = None
        self.__positionShort = None
        self.__position = None
        self.__State=0
        self.__criteria=None
        self.__t = None
        self.getBroker().setAllowNegativeCash(True)
        self.__execInfo = "0,0"

    @property
    def getBollingerBands_upper(self):
        return self.__bbands_upper
    @property
    def getBollingerBands_lower(self):
        return self.__bbands_lower

    def onEnterOk(self, position):
        self.__execInfo = position.getEntryOrder().getExecutionInfo()
        if position.getEntryOrder().isBuy():
            side="BUY"
        else:
            side="SELL"

        self.__execInfo =str(position.getEntryOrder().getAvgFillPrice()) + "," + side#, "***", position.getEntryOrder().getId()

        #self.stopOrder(self.__instrument,)
        # self.info("EXECUTION at $%.6f :: %.6f" % (execInfo.getPrice(),position.getEntryOrder().getState() ))
        # self.__position.exitStop(execInfo.getPrice() * 0.95, True)
        #self.info(position.getEntryOrder())

    def onOrderUpdated(self, order):
        if order.isFilled():
            order.getExecutionInfo().getPrice()
    def onExitOk(self, position):
        execInfo = position.getEntryOrder().getExecutionInfo()
        # print execInfo
        # self.info("SELL at $%.6f" % (execInfo.getPrice()))
        # self.__position.exitStop(execInfo.getPrice() * 0.95, True)

    # def onExitCanceled(self, position):
    #     # If the exit was canceled, re-submit it.
    #     self.__position.exitMarket()



    def onEnterCanceled(self, position):
        self.__positionLong = None
        self.__positionShort = None
    # def onExitCanceled(self, position):
    #     self.__positionLong = None
    #     self.__positionShort = None

    def onBars(self, bars):
        bar = bars[self.__instrument]
    # State 0: Nothing happened at the previous bar
    #       1: Crossed below the lower Bollinger band at the previous bar
    #       2: Crossed above the upper Bollinger band at the previous bar
        if not len(self.getBroker().getPositions()) == 0:
            carry = self.getBroker().getPositions()[self.__instrument]
        else:
            carry = 0
        if not self.__positionLong is None:
            # self.info(self.__positionLong.getAge().seconds)
            self.__positionLong.cancelEntry()
            self.__positionLong = None
            # self.__positionLong.exitMarket()
        if not self.__positionShort is None :
            # self.info( self.__positionShort.getAge().seconds)
            self.__positionShort.cancelEntry()
            self.__positionShort = None
            #self.__positionShort.exitMarket()
            self.__positionShort=None

        lower = self.__bbands_lower.getLowerBand()[-1]
        upper = self.__bbands_upper.getUpperBand()[-1]
        #if( lower== None or upper== None):
         #   print("%s,%f,%f,%f,%f,,,," % (bar.getDateTime(),bar.getOpen(), bar.getHigh(), bar.getLow(), bar.getClose()))
        #else:
            #print("%s,%f,%f,%f,%f,%f,%f,%s" %(bar.getDateTime(),bar.getOpen(),bar.getHigh(),bar.getLow(),bar.getClose(),lower, upper, self.__execInfo))
        # print("lower: %s" % lower)
        # shares = self.getBroker().getShares(self.__instrument)


        baseshare = 300000

        State = self.__State
        # print self.__bbands_lower.getLowerBand()[-1],self.__bbands_lower.getLowerBand()[0],self.__bbands_upper.getUpperBand()[-1],self.__bbands_upper.getUpperBand()[0]
        if State==0:
            if cross.cross_above(self.__prices, self.__bbands_lower.getLowerBand()):
                State = 1
                self.__criteria=lower
                #self.info("Bolingeri asagidan kirdi (%.4f > %.4f). "
                #          "Bar range: %.4f - %.4f "
                #          % (self.__prices[-1], lower,bar.getLow(), bar.getHigh()))
            elif cross.cross_below(self.__prices, self.__bbands_upper.getUpperBand()):
                State=2
                self.__criteria=upper
        if State==1:
            self.__State = 0
        # if bar.getClose() > self.__criteria and bar.getLow() < self.__criteria:
            # print cross.cross_above(self.__prices, self.__bbands_lower.getLowerBand())
            #self.__positionLong = self.enterLong(self.__instrument, sharesToBuy, True)
            self.__positionLong = self.enterLongStop(self.__instrument,self.__criteria, baseshare+abs(min(0,carry)), False)
            #self.info("%i Buy order @$%.6f. Cash: %s " % (baseshare, lower, self.getBroker().getPositions()))
            #self.info("Order ID %i:" % self.__positionLong.getEntryOrder().getId())
        elif State==2:
            self.__State = 0
            #if bar.getClose() < self.__criteria:
            # if cross.cross_below(self.__prices, self.__bbands_lower.getUpperBand()) > 0:
            self.__positionShort = self.enterShortStop(self.__instrument,self.__criteria,baseshare+abs(max(0, carry)),False)
            #self.info(" Sell %dK @$%.6f. Cash: %s. Order ID: %i " %
            #          (baseshare/1000, upper, self.getBroker().getPositions(),self.__positionShort.getEntryOrder().getId() )
            #          )
        self.__execInfo = "0,0"


            #
        #     if not self.__positionShort == None:
        #         if not self.__positionShort.exitActive():
        #             self.__positionShort.exitMarket()
        #
        #     sharesToBuy = int(baseshare)
        #     self.__positionLong = self.enterLong(self.__instrument,sharesToBuy, True)
        #     self.info("%i Buy order @$%.6f . Cash: %s " % (sharesToBuy, lower,self.getBroker().getCash(False)))
        #
        # elif cross.cross_above(self.__prices, self.__bbands_upper.getUpperBand()) > 0:
        #     if not self.__positionLong == None:
        #         if not self.__positionLong.exitActive():
        #             self.__positionLong.exitMarket()
        #
        #     sharesToBuy = int(baseshare)
        #     self.__positionShort = self.enterShort(self.__instrument,sharesToBuy,True)
        #     self.info("%i Sell order @$%.6f . Cash: %s " % (sharesToBuy, upper,self.getBroker().getCash(True)))
def main(plot):
    instrument = "eurusd"
    bBandsPeriod_upper = 40
    bBandsPeriod_lower = 20

    # Download the bars.
    feed= csvfeed.GenericBarFeed(bar.Frequency.HOUR)
    # feed1.setDateTimeFormat("%Y-%m-%d %H:%M:%S")
    feed.addBarsFromCSV(instrument,"/Users/hrn/PycharmProjects/eurusd.csv")

    strat = BBands(feed, instrument, bBandsPeriod_upper,bBandsPeriod_lower)
    sharpeRatioAnalyzer = sharpe.SharpeRatio()
    strat.attachAnalyzer(sharpeRatioAnalyzer)

    if plot:
        plt = plotter.StrategyPlotter(strat, True, True, True)
        plt.getInstrumentSubplot(instrument).addDataSeries("upper", strat.getBollingerBands_upper.getUpperBand())
        # plt.getInstrumentSubplot(instrument).addDataSeries("middle", strat.getBollingerBands().getMiddleBand())
        plt.getInstrumentSubplot(instrument).addDataSeries("lower", strat.getBollingerBands_lower.getLowerBand())
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
