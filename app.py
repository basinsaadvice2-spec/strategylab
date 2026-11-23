
import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
import plotly.graph_objects as go
from datetime import date, timedelta

st.set_page_config(page_title="StrategyLab", page_icon="📈", layout="wide")

@st.cache_data(ttl=3600, show_spinner=False)
def get_data(symbol, start, end, interval):
    x = yf.download(symbol, start=start, end=end + timedelta(days=1),
                    interval=interval, auto_adjust=False, progress=False, threads=False)
    if x is None or x.empty:
        return pd.DataFrame()
    if isinstance(x.columns, pd.MultiIndex):
        x.columns = x.columns.get_level_values(0)
    cols = ["Open", "High", "Low", "Close"]
    if not set(cols).issubset(x.columns):
        return pd.DataFrame()
    x = x[cols + (["Volume"] if "Volume" in x else [])].copy()
    for c in x:
        x[c] = pd.to_numeric(x[c], errors="coerce")
    x = x.replace([np.inf, -np.inf], np.nan).dropna(subset=cols)
    x = x[(x[cols] > 0).all(axis=1) & (x.High >= x.Low)]
    if "Volume" not in x:
        x["Volume"] = 0.0
    x["Volume"] = x.Volume.fillna(0).clip(lower=0)
    x.index = pd.to_datetime(x.index)
    if x.index.tz is not None:
        x.index = x.index.tz_localize(None)
    return x.sort_index()

def make_indicators(x):
    c,h,l,o,v = x.Close,x.High,x.Low,x.Open,x.Volume
    def sma(s,n): return s.rolling(n,min_periods=n).mean()
    def ema(s,n): return s.ewm(span=n,adjust=False,min_periods=n).mean()
    def wma(s,n):
        w=np.arange(1,n+1,dtype=float)
        return s.rolling(n,min_periods=n).apply(lambda a: np.dot(a,w)/w.sum(),raw=True)
    def rsi(s,n):
        d=s.diff(); up=d.clip(lower=0); dn=-d.clip(upper=0)
        a=up.ewm(alpha=1/n,adjust=False,min_periods=n).mean()
        b=dn.ewm(alpha=1/n,adjust=False,min_periods=n).mean()
        z=100-100/(1+a/b.replace(0,np.nan))
        return z.mask((b==0)&(a>0),100).mask((a==0)&(b>0),0)
    tr=pd.concat([h-l,(h-c.shift()).abs(),(l-c.shift()).abs()],axis=1).max(axis=1)
    def atr(n): return tr.ewm(alpha=1/n,adjust=False,min_periods=n).mean()
    z=pd.DataFrame(index=x.index)
    for n in [5,10,20,50,100,200]: z[f"SMA {n}"]=sma(c,n)
    for n in [5,9,12,20,26,50,100,200]: z[f"EMA {n}"]=ema(c,n)
    for n in [5,10,20,50]: z[f"WMA {n}"]=wma(c,n)
    z["HMA 20"]=wma(2*wma(c,10)-wma(c,20),4)
    z["VWMA 20"]=(c*v).rolling(20).sum()/v.rolling(20).sum().replace(0,np.nan)
    for n in [7,14,21]: z[f"RSI {n}"]=rsi(c,n)
    m=ema(c,12)-ema(c,26); ms=ema(m,9)
    z["MACD"]=m; z["MACD Signal"]=ms; z["MACD Histogram"]=m-ms
    lo14=l.rolling(14).min(); hi14=h.rolling(14).max()
    z["Stochastic K"]=100*(c-lo14)/(hi14-lo14).replace(0,np.nan)
    z["Stochastic D"]=z["Stochastic K"].rolling(3).mean()
    z["Williams %R"]=-100*(hi14-c)/(hi14-lo14).replace(0,np.nan)
    tp=(h+l+c)/3
    z["CCI 20"]=(tp-sma(tp,20))/(.015*tp.rolling(20).apply(lambda a: np.mean(np.abs(a-np.mean(a)))))
    z["ROC 10"]=c.pct_change(10)*100; z["Momentum 10"]=c-c.shift(10)
    z["TRIX 15"]=ema(ema(ema(c,15),15),15).pct_change()*100
    z["PPO"]=(ema(c,12)-ema(c,26))/ema(c,26)*100
    mid=sma(c,20); sd=c.rolling(20).std()
    z["Bollinger Middle"]=mid; z["Bollinger Upper"]=mid+2*sd; z["Bollinger Lower"]=mid-2*sd
    z["Bollinger Width"]=4*sd/mid*100; z["Bollinger %B"]=(c-(mid-2*sd))/(4*sd).replace(0,np.nan)
    z["ATR 7"]=atr(7); z["ATR 14"]=atr(14); z["NATR 14"]=atr(14)/c*100
    up=h.diff(); dn=-l.diff()
    pdm=up.where((up>dn)&(up>0),0); mdm=dn.where((dn>up)&(dn>0),0)
    z["DI Plus"]=100*pdm.ewm(alpha=1/14,adjust=False).mean()/atr(14)
    z["DI Minus"]=100*mdm.ewm(alpha=1/14,adjust=False).mean()/atr(14)
    dx=100*(z["DI Plus"]-z["DI Minus"]).abs()/(z["DI Plus"]+z["DI Minus"])
    z["ADX 14"]=dx.ewm(alpha=1/14,adjust=False).mean()
    z["Donchian Upper"]=h.rolling(20).max().shift(1); z["Donchian Lower"]=l.rolling(20).min().shift(1)
    z["Keltner Middle"]=ema(c,20); z["Keltner Upper"]=ema(c,20)+2*atr(10); z["Keltner Lower"]=ema(c,20)-2*atr(10)
    z["OBV"]=(np.sign(c.diff()).fillna(0)*v).cumsum()
    mf=tp*v; pos=mf.where(tp.diff()>0,0).rolling(14).sum(); neg=mf.where(tp.diff()<0,0).rolling(14).sum()
    z["MFI 14"]=100-100/(1+pos/neg.replace(0,np.nan))
    mfm=((c-l)-(h-c))/(h-l).replace(0,np.nan)
    z["Chaikin Money Flow"]=(mfm*v).rolling(20).sum()/v.rolling(20).sum().replace(0,np.nan)
    z["Accumulation Distribution"]=(mfm*v).cumsum()
    z["VWAP Cumulative"]=(tp*v).cumsum()/v.cumsum().replace(0,np.nan)
    z["Aroon Up"]=h.rolling(25).apply(lambda a:100*(np.argmax(a)+1)/25,raw=True)
    z["Aroon Down"]=l.rolling(25).apply(lambda a:100*(np.argmin(a)+1)/25,raw=True)
    ten=(h.rolling(9).max()+l.rolling(9).min())/2
    kij=(h.rolling(26).max()+l.rolling(26).min())/2
    z["Ichimoku Tenkan"]=ten; z["Ichimoku Kijun"]=kij
    z["Ichimoku Span A"]=(ten+kij)/2; z["Ichimoku Span B"]=(h.rolling(52).max()+l.rolling(52).min())/2
    z["DPO 20"]=c.shift(11)-sma(c,20)
    prev=c.shift()
    bp=c-pd.concat([l,prev],axis=1).min(axis=1)
    tr_u=pd.concat([h,prev],axis=1).max(axis=1)-pd.concat([l,prev],axis=1).min(axis=1)
    u7=bp.rolling(7).sum()/tr_u.rolling(7).sum()
    u14=bp.rolling(14).sum()/tr_u.rolling(14).sum()
    u28=bp.rolling(28).sum()/tr_u.rolling(28).sum()
    z["Ultimate Oscillator"]=100*(4*u7+2*u14+u28)/7
    ch=c.diff()
    z["TSI"]=100*ema(ema(ch,25),13)/ema(ema(ch.abs(),25),13)
    vol=c.rolling(10).std(); vu=ema(vol.where(ch>0,0),14); vd=ema(vol.where(ch<0,0),14)
    z["RVI"]=100*vu/(vu+vd).replace(0,np.nan)
    z["High Low Range"]=h-l; z["Open Close Change %"]=(c/o-1)*100
    z["Close Location Value"]=((c-l)-(h-c))/(h-l).replace(0,np.nan)
    z["Gap %"]=(o-c.shift())/c.shift()*100; z["Daily Return %"]=c.pct_change()*100
    return pd.concat([x,z],axis=1)

def condition(d, rule):
    name,op,val=rule; s=d[name]
    if op=="Above": return s>val
    if op=="Below": return s<val
    if op=="Crosses above": return (s>val)&(s.shift()<=val)
    return (s<val)&(s.shift()>=val)

def combine(d,rules,mode):
    arr=[condition(d,r).fillna(False) for r in rules]
    ans=arr[0]
    for a in arr[1:]: ans=(ans&a) if mode=="ALL" else (ans|a)
    return ans

def simulate(d, buy, sell, capital, allocation, commission, spread, slip, stop, target):
    # Long-only, no leverage. Signal close -> execution next bar open.
    d=d.copy(); buy=buy.shift(1).astype("boolean").fillna(False); sell=sell.shift(1).astype("boolean").fillna(False)
    cash=float(capital); qty=0.; entry=0.; entry_date=None; cost=0.
    fees=(commission+spread/2+slip)/100
    eq=[]; rows=[]
    for dt,r in d.iterrows():
        op,hi,lo,cl=map(float,[r.Open,r.High,r.Low,r.Close]); closed=False
        if qty:
            sp=entry*(1-stop/100) if stop else None
            tp=entry*(1+target/100) if target else None
            sh=sp is not None and lo<=sp; th=tp is not None and hi>=tp
            if sh or th:
                raw=(min(op,sp) if op<sp else sp) if sh else (max(op,tp) if op>tp else tp)
                proceeds=qty*raw*(1-fees); pnl=proceeds-cost
                rows.append([entry_date,dt,entry,raw,pnl,pnl/cost*100,"Stop-loss" if sh else "Take-profit"])
                cash+=proceeds; qty=0.; entry=0.; entry_date=None; cost=0.; closed=True
        if qty and bool(sell.loc[dt]) and not closed:
            raw=op; proceeds=qty*raw*(1-fees); pnl=proceeds-cost
            rows.append([entry_date,dt,entry,raw,pnl,pnl/cost*100,"Signal de sortie"])
            cash+=proceeds; qty=0.; entry=0.; entry_date=None; cost=0.; closed=True
        if not qty and bool(buy.loc[dt]) and not closed and cash>0:
            budget=cash*allocation/100; fill=op*(1+fees)
            qty=budget/fill; cash-=budget; cost=budget; entry=fill; entry_date=dt
        eq.append(cash+qty*cl)
    d["Equity"]=eq; d["Buy & Hold"]=capital*d.Close/d.Close.iloc[0]
    d["Peak"]=d.Equity.cummax(); d["Drawdown %"]=(d.Equity/d.Peak-1)*100
    if qty:
        dt=d.index[-1]; raw=float(d.Close.iloc[-1]); proceeds=qty*raw*(1-fees); pnl=proceeds-cost
        rows.append([entry_date,dt,entry,raw,pnl,pnl/cost*100,"Fin du test"])
        d.loc[dt,"Equity"]=cash+proceeds
        d["Peak"]=d.Equity.cummax(); d["Drawdown %"]=(d.Equity/d.Peak-1)*100
    trades=pd.DataFrame(rows,columns=["Entrée","Sortie","Prix entrée coûts inclus","Prix sortie brut","P/L net","Rendement net %","Motif"])
    return d,trades

st.title("StrategyLab")
st.caption("Backtesting historique sur données téléchargées. Aucun cours de démonstration ou prix inventé.")
with st.sidebar:
    st.header("Marché")
    asset=st.selectbox("Actif",["Or — Gold Futures (GC=F)","Pétrole WTI Futures (CL=F)"])
    symbol="GC=F" if asset.startswith("Or") else "CL=F"
    freq=st.selectbox("Fréquence",["Quotidienne","Horaire","30 minutes","15 minutes"])
    interval={"Quotidienne":"1d","Horaire":"1h","30 minutes":"30m","15 minutes":"15m"}[freq]
    today=date.today(); start=st.date_input("Début",today-timedelta(days=365*3),max_value=today)
    end=st.date_input("Fin",today,max_value=today)
    refresh=st.button("Actualiser les données")
    st.divider(); st.header("Conditions de stratégie")
    names=["SMA 5","SMA 10","SMA 20","SMA 50","SMA 100","SMA 200","EMA 5","EMA 9","EMA 12","EMA 20","EMA 26","EMA 50","EMA 100","EMA 200","WMA 5","WMA 10","WMA 20","WMA 50","HMA 20","VWMA 20","RSI 7","RSI 14","RSI 21","MACD","MACD Signal","MACD Histogram","Stochastic K","Stochastic D","Williams %R","CCI 20","ROC 10","Momentum 10","TRIX 15","PPO","Bollinger Middle","Bollinger Upper","Bollinger Lower","Bollinger Width","Bollinger %B","ATR 7","ATR 14","NATR 14","DI Plus","DI Minus","ADX 14","Donchian Upper","Donchian Lower","Keltner Middle","Keltner Upper","Keltner Lower","OBV","MFI 14","Chaikin Money Flow","Accumulation Distribution","VWAP Cumulative","Aroon Up","Aroon Down","Ichimoku Tenkan","Ichimoku Kijun","Ichimoku Span A","Ichimoku Span B","DPO 20","Ultimate Oscillator","TSI","RVI","High Low Range","Open Close Change %","Close Location Value","Gap %","Daily Return %"]
    st.caption(f"{len(names)} indicateurs et mesures calculés localement.")
    def editor(key,title,defaults):
        st.subheader(title); n=st.number_input("Nombre de règles",1,5,len(defaults),key=key+"n")
        rules=[]
        for i in range(int(n)):
            a,b,c=st.columns([1.5,1.1,.8])
            default=defaults[min(i,len(defaults)-1)]
            nm=a.selectbox("Indicateur",names,index=names.index(default[0]),key=key+"i"+str(i))
            op=b.selectbox("Opérateur",["Above","Below","Crosses above","Crosses below"],index=["Above","Below","Crosses above","Crosses below"].index(default[1]),key=key+"o"+str(i))
            val=c.number_input("Valeur",value=float(default[2]),key=key+"v"+str(i))
            rules.append((nm,op,val))
        mode=st.radio("Combiner",["ALL","ANY"],horizontal=True,key=key+"mode")
        return rules,mode
    buy_rules,buy_mode=editor("buy","Entrée / Achat",[("RSI 14","Below",30),("MACD Histogram","Above",0)])
    sell_rules,sell_mode=editor("sell","Sortie / Vente",[("RSI 14","Above",70),("MACD Histogram","Below",0)])
    st.divider(); st.header("Capital et frais")
    capital=st.number_input("Capital initial ($)",100.,value=10000.,step=500.)
    allocation=st.slider("Capital engagé par position (%)",1,100,100)
    commission=st.number_input("Commission par côté (%)",0.,5.,.05,.01)
    spread=st.number_input("Spread total estimé (%)",0.,5.,.02,.01)
    slippage=st.number_input("Slippage par côté (%)",0.,5.,.02,.01)
    stop=st.number_input("Stop-loss (%) — 0 désactivé",0.,90.,0.,.5)
    target=st.number_input("Take-profit (%) — 0 désactivé",0.,300.,0.,.5)

if start>=end: st.error("La date de début doit précéder la date de fin."); st.stop()
if refresh: get_data.clear()
if interval!="1d" and (today-start).days>60:
    st.warning("Les données intrajournalières Yahoo ont une profondeur limitée. Réduis la période si aucun historique n'est renvoyé.")
with st.spinner("Téléchargement des cours réels..."):
    try: raw=get_data(symbol,start,end,interval)
    except Exception as e: st.error(f"Erreur du fournisseur de données : {e}"); st.stop()
if raw.empty:
    st.error("Aucune donnée renvoyée par Yahoo Finance. Aucun cours fictif ne sera substitué."); st.stop()
if len(raw)<60: st.error(f"Historique insuffisant : {len(raw)} bougies seulement."); st.stop()

d=make_indicators(raw)
buy=combine(d,buy_rules,buy_mode); sell=combine(d,sell_rules,sell_mode)
valid=d[[r[0] for r in buy_rules+sell_rules]].notna().all(axis=1)
buy &= valid; sell &= valid
res,trades=simulate(d,buy,sell,capital,allocation,commission,spread,slippage,stop,target)
final=float(res.Equity.iloc[-1]); ret=(final/capital-1)*100
bh=(float(res["Buy & Hold"].iloc[-1])/capital-1)*100
dd=float(res["Drawdown %"].min())
wins=trades[trades["P/L net"]>0]; losses=trades[trades["P/L net"]<0]
winrate=len(wins)/len(trades)*100 if len(trades) else 0
gp=wins["P/L net"].sum() if len(wins) else 0
gl=abs(losses["P/L net"].sum()) if len(losses) else 0
pf=gp/gl if gl else (np.inf if gp else 0)
st.subheader(asset)
st.caption(f"{len(raw):,} bougies téléchargées · {raw.index[0]} au {raw.index[-1]} · Yahoo Finance · cache 1 heure")
a,b,c,e=st.columns(4); a.metric("Capital final",f"${final:,.2f}",f"{ret:+.2f}%"); b.metric("Buy & Hold",f"{bh:+.2f}%"); c.metric("Drawdown max",f"{dd:.2f}%"); e.metric("Taux gagnant",f"{winrate:.1f}%")
a,b,c,e=st.columns(4); a.metric("Transactions",len(trades)); b.metric("Profit Factor","∞" if np.isinf(pf) else f"{pf:.2f}"); c.metric("P/L net",f"${final-capital:,.2f}"); e.metric("Allocation",f"{allocation}%")
t1,t2,t3,t4=st.tabs(["Prix et indicateurs","Capital et drawdown","Transactions","Données"])
with t1:
    fig=go.Figure(go.Candlestick(x=res.index,open=res.Open,high=res.High,low=res.Low,close=res.Close,name="Cours téléchargés"))
    for nm in dict.fromkeys(r[0] for r in buy_rules+sell_rules):
        fig.add_trace(go.Scatter(x=res.index,y=res[nm],name=nm))
    fig.update_layout(height=600,xaxis_rangeslider_visible=False,hovermode="x unified",title="Cours historiques et indicateurs")
    st.plotly_chart(fig,use_container_width=True)
with t2:
    f=go.Figure(); f.add_trace(go.Scatter(x=res.index,y=res.Equity,name="Stratégie",fill="tozeroy")); f.add_trace(go.Scatter(x=res.index,y=res["Buy & Hold"],name="Buy & Hold"))
    f.update_layout(height=380,title="Évolution du capital",hovermode="x unified"); st.plotly_chart(f,use_container_width=True)
    g=go.Figure(go.Scatter(x=res.index,y=res["Drawdown %"],name="Drawdown",fill="tozeroy")); g.update_layout(height=280,title="Drawdown (%)"); st.plotly_chart(g,use_container_width=True)
with t3:
    if trades.empty: st.info("Aucune transaction générée avec ces conditions.")
    else:
        st.dataframe(trades,use_container_width=True,hide_index=True)
        st.download_button("Exporter transactions CSV",trades.to_csv(index=False).encode(),"trades.csv","text/csv")
with t4:
    st.dataframe(res.tail(1000),use_container_width=True)
    st.download_button("Exporter données CSV",res.to_csv().encode(),"strategylab_data.csv","text/csv")

with st.expander("Méthodologie et limites importantes"):
    st.markdown("""
- Les cours proviennent du téléchargement Yahoo Finance des symboles GC=F (contrat à terme continu sur l'or) et CL=F (contrat à terme continu WTI). Ils ne sont pas nécessairement identiques aux cours spot/CFD du courtier.
- Aucun cours de démonstration, aléatoire ou synthétique n'est utilisé dans l'application.
- Les règles sont évaluées à la clôture; l'exécution simulée intervient à l'ouverture de la bougie suivante.
- Simulation longue uniquement, sans levier ni vente à découvert. Une position maximum.
- Les commissions, spread et slippage sont des hypothèses modifiables; entre les coûts réels du courtier pour une meilleure approximation.
- Stop et objectif sont évalués sur le haut/bas de la bougie. Si les deux sont touchés, le stop est prioritaire.
- Le financement overnight, marge, appels de marge, rollover détaillé et règles du courtier ne sont pas modélisés : le résultat n'est pas une reproduction garantie du compte réel.
- Yahoo peut limiter ou retarder les données. Actualisation manuelle possible; cache d'une heure. Une nouvelle bougie apparaît seulement après publication par le fournisseur.
- Les indicateurs sont calculés localement à partir des cours téléchargés; les indicateurs de volume peuvent être peu pertinents si le fournisseur ne donne pas de volume fiable.
""")
st.caption("StrategyLab — outil de simulation historique, sans connexion à un courtier ni transmission d'ordres.")
