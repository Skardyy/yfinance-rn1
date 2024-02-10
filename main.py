import yfinance as yf
from requests import Session
from requests_cache import CacheMixin, SQLiteCache
from requests_ratelimiter import LimiterMixin, MemoryQueueBucket
from pyrate_limiter import Duration, RequestRate, Limiter
import pandas as pd

class CachedLimiterSession(CacheMixin, LimiterMixin, Session):
    pass

session = CachedLimiterSession(
    limiter=Limiter(RequestRate(2, Duration.SECOND*5)),  # max 2 requests per 5 seconds
    bucket_class=MemoryQueueBucket,
    backend=SQLiteCache("yfinance.cache"),
)

def getTickerData(ticker, session) -> tuple[pd.DataFrame, pd.DataFrame]:
    data = yf.Ticker(ticker, session)

    #basic
    income_stmt = data.financials.loc[['Operating Income', 'Tax Provision', 'Total Revenue', 'Diluted EPS'], :]
    balance_sheet = data.balance_sheet.loc[['Invested Capital', 'Common Stock Equity'], :]
    ttm_eps = data.info['trailingEps']
    pe = data.info['trailingPE']
    free_cash_flow = data.cash_flow.loc[['Free Cash Flow'], :]

    #calculating roic
    tax_rate = income_stmt.loc['Tax Provision'] / income_stmt.loc['Operating Income']
    nopat = income_stmt.loc['Operating Income'] * (1 - tax_rate)
    roic = nopat / balance_sheet.loc['Invested Capital']

    df = pd.DataFrame({
        'Revenue': income_stmt.loc['Total Revenue'],
        'Equity': balance_sheet.loc['Common Stock Equity'],
        'FCF': free_cash_flow.loc['Free Cash Flow'],
        'EPS': income_stmt.loc['Diluted EPS'],
        'TTM EPS': ttm_eps,
        'PE': pe,
        'ROIC': roic
    })

    #calculating growths
    df = df[::-1]
    df['Revenue Growth'] = ((df['Revenue'] - df['Revenue'].shift(1)) / df['Revenue'].shift(1)) * 100
    df['Equity Growth'] = ((df['Equity'] - df['Equity'].shift(1)) / df['Equity'].shift(1)) * 100
    df['FCF Growth'] = ((df['FCF'] - df['FCF'].shift(1)) / df['FCF'].shift(1)) * 100
    df['EPS Growth'] = ((df['EPS'] - df['EPS'].shift(1)) / df['EPS'].shift(1)) * 100
    df['ROIC Growth'] = ((df['ROIC'] - df['ROIC'].shift(1)) / df['ROIC'].shift(1)) * 100

    #calculating avg and checking if passes
    avg_revenue_growth = df['Revenue Growth'].mean()
    avg_equity_growth = df['Equity Growth'].mean()
    avg_fcf_growth = df['FCF Growth'].mean()
    avg_eps_growth = df['EPS Growth'].mean()
    avg_roic_growth = df['ROIC Growth'].mean()

    checking_df = pd.DataFrame({
        'Avg Revenue Growth': [avg_revenue_growth],
        'Avg Equity Growth': [avg_equity_growth],
        'Avg FCF Growth': [avg_fcf_growth],
        'Avg EPS Growth': [avg_eps_growth],
        'Avg ROIC Growth': [avg_roic_growth]
    })
    checking_df['All Above 10'] = (checking_df > 10).all(axis=1)
    checking_df['PE'] = [min([pe, avg_eps_growth * 2])]
    checking_df['TTM_EPS'] = ttm_eps
    future_eps = avg_equity_growth
    checking_df['Future EPS'] = future_eps

    checking_df['Price in 10 years'] = ttm_eps ** (10 / (72/future_eps)) * pe

    return df, checking_df

ticker = "MSFT"
historical_df, final_df = getTickerData(ticker, session)

#print("historical data\n", historical_df)
#print("checking data\n", final_df)