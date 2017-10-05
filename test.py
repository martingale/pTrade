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


import datetime
import csv
from joblib import Parallel, delayed
from pyalgotrade.utils import csvutils


class RowParser(csvfeed.RowParser):
    def __init__(self):
        self.__prevClose=None
    def getFieldNames(self):
        # It is expected for the first row to have the field names.
        return None

    def getDelimiter(self):
        return ","

    def parseBar(self, csvRowDict):

        dateTime = datetime.datetime.strptime(csvRowDict["date_time"], "%Y-%m-%d %H:%M:%S.%f")
        close= float(csvRowDict["price"])
        if not self.__prevClose is None:
            open=self.__prevClose
        else:
            open=close
        volume = float(csvRowDict["quantity"])
        high=max(close,open)
        low = min(close, open)
        thisbar=bar.BasicBar(dateTime, open, high, low, close, volume, close, None)
        self.__prevClose=close

        return thisbar

        if timezone is None:
            timezone = self.__timezone

        rowParser = GenericRowParser(
            self.__columnNames, self.__dateTimeFormat, self.getDailyBarTime(), self.getFrequency(),
            timezone, self.__barClass
        )

        super(GenericBarFeed, self).addBarsFromCSV(instrument, path, rowParser)

        if rowParser.barsHaveAdjClose():
            self.__haveAdjClose = True
        elif self.__haveAdjClose:
            raise Exception("Previous bars had adjusted close and these ones don't have.")

class Feed(csvfeed.BarFeed):
    def __init__(self):
        csvfeed.BarFeed.__init__(self, barfeed.Frequency.TRADE, maxLen=dataseries.DEFAULT_MAX_LEN)

    def barsHaveAdjClose(self):
        return False

    def addBarsFromCSV(self, instrument, path,m):
        rowParser = RowParser()
        k = 0
        loadedBars = []
        reader = csvutils.FastDictReader(open(path, "r"), fieldnames=rowParser.getFieldNames(),
                                         delimiter=rowParser.getDelimiter())
        for row in reader:
            k = k + 1
            if k % m == 0:
                bar_ = rowParser.parseBar(row)
                if bar_ is not None:
                    loadedBars.append(bar_)
            else:
                pass

        self.addBarsFromSequence(instrument, loadedBars)


class SMACrossOver(strategy.BacktestingStrategy):
    def __init__(self, feed, instrument, smaPeriod):
        super(SMACrossOver, self).__init__(feed)
        self.__instrument = instrument
        self.__position = None
        # We'll use adjusted close values instead of regular close values.
        # self.setUseAdjustedValues(False)
        self.__prices = feed[instrument].getPriceDataSeries()
        self.__sma = ma.SMA(self.__prices, smaPeriod)
        self.__execInfo = "0,0"

    def getSMA(self):
        return self.__sma

    def onEnterCanceled(self, position):
        self.__position = None

    def onExitOk(self, position):
        self.__position = None
        self.__execInfo = str(position.getExitOrder().getAvgFillPrice()) + "," +str(self.__sma[-1])+ ", SELL\n"   # , "***", position.getEntryOrder().getId()
        # self.info(position.getEntryOrder())
        self.info(self.__execInfo)
    def onExitCanceled(self, position):
        # If the exit was canceled, re-submit it.
        self.__position.exitMarket()
    def onEnterOk(self, position):
        # self.__execInfo = position.getEntryOrder().getExecutionInfo()
        if position.getEntryOrder().isBuy():
            side = "BUY"
        else:
            side = "SELL"

        self.__execInfo = str(position.getEntryOrder().getAvgFillPrice()) + "," +str(self.__sma[-1])+", "+ side + " " +\
                          str(position.getEntryOrder().getFilled()) # , "***", position.getEntryOrder().getId()
        # self.info(position.getEntryOrder())
        self.info(self.__execInfo)
        # self.info(position.getEntryOrder().getExecutionInfo())
    def onBars(self, bars):
        # If a position was not opened, check if we should enter a long position.
        if self.__position is None:
            if self.__sma[-1] is not None and self.__prices[-1]< (self.__sma[-1] - .01) :
                shares=100000
                shares = int(.9 * self.getBroker().getCash()  / bars[self.__instrument].getPrice())
                # Enter a buy market order. The order is good till canceled.
                self.__position = self.enterLong(self.__instrument, shares, True)
                 # Check if we have to exit the position.
        elif not self.__position.exitActive() and cross.cross_above(self.__prices, self.__sma) > 0:
            #self.info("ciktik\n")
            self.__position.exitMarket()
        bar = bars[self.__instrument]
        if self.__sma[-1] is None:
            smaLast=0
        else:
            smaLast=self.__sma[-1]
        #print("%s,%f,%f,%f,%f,%f" % (bar.getDateTime(), bar.getOpen(), bar.getHigh(), bar.getLow(), bar.getClose(),smaLast))

        info=str(bar.getOpen())+ "-" + str(bar.getHigh())+ "-" + str(bar.getLow())+"-"+ str(bar.getClose())+ "-"+str(smaLast)
        self.info(info)
def runAllStrat(m, k):
    instrument = "garan"
    feed = Feed()
    feed.addBarsFromCSV(instrument, "gran.csv", m)
    strat = SMACrossOver(feed, instrument, k)
    strat.getBroker().setCommission(backtesting.TradePercentage(0.0003))

    tradesAnalyzer = trades.Trades()

    b=feed.getLastBar(instrument)
    strat.attachAnalyzer(tradesAnalyzer)
    strat.run()
    print "# of trades:%i\n" % (tradesAnalyzer.getCount())

    print "%i,%i....Final portfolio value: $%.2f:" % (m,k,strat.getBroker().getEquity())
    return strat.getBroker().getEquity()

def main():
    nticks=range(5, 100 + 1, 1)
    nsma=range(100, 500 + 1, 5)
    #data = Parallel(n_jobs=16)(delayed(runAllStrat)(m=i, k=j) for i in nticks for j in nsma)
    data = Parallel(n_jobs=1)(delayed(runAllStrat)(m=i, k=j) for i in range(80, 81,1) for j in range(100, 101,1))

    data= np.matrix(data)
    nrow=len(nticks)
    ncol= len(nsma)
    data=np.resize(data,(nrow,ncol))
    data=pd.DataFrame(data)
    # data.columns=nticks
    # data.index=nsma
    # data.to_csv("outJunl.csv",index_label = 'n_ticks|n_ma')

#    with open('outJunk.csv', 'w') as out:
#       writer = csv.writer(out)
#      writer.writerow(data)

if __name__ == "__main__":
    main()
