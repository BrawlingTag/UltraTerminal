import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go

st.set_page_config(page_title="Ultrascore Screener", page_icon="📈", layout="wide")

# ------------------------------------------------------------
# Aktien-Universum (80 Large- und Mega-Caps weltweit)
# ------------------------------------------------------------
REGIONEN = {
    "USA": ["AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "BRK-B", "JPM", "V", "MA",
            "JNJ", "UNH", "LLY", "PG", "XOM", "KO", "PEP", "COST", "WMT", "HD",
            "AVGO", "ORCL", "ADBE", "CRM", "MRK"],
    "Europa": ["SAP.DE", "SIE.DE", "ALV.DE", "MC.PA", "OR.PA", "TTE.PA", "AIR.PA", "SAN.PA",
               "RMS.PA", "ASML.AS", "NESN.SW", "NOVN.SW", "ROG.SW", "NOVO-B.CO", "AZN.L",
               "SHEL.L", "ULVR.L", "HSBA.L", "ITX.MC", "ENEL.MI"],
    "Japan": ["7203.T", "6758.T", "8306.T", "6861.T", "9983.T", "8035.T", "9432.T", "4063.T"],
    "China/Hongkong": ["0700.HK", "9988.HK", "1299.HK", "0939.HK", "1211.HK", "3690.HK",
                       "0941.HK", "2318.HK"],
    "Taiwan/Korea": ["2330.TW", "2317.TW", "005930.KS", "000660.KS"],
    "Indien": ["RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "INFY.NS", "ICICIBANK.NS"],
    "Sonstige": ["RY.TO", "SHOP.TO", "ENB.TO", "BHP.AX", "CBA.AX", "CSL.AX",
                 "VALE3.SA", "PETR4.SA", "ITUB4.SA", "2222.SR"],
}

# Ist ein hoher Wert gut (True) oder schlecht (False)?
RICHTUNG = {
    "Schwankung": False,
    "Marge": True,
    "ROE": True,
    "FCF-Marge": True,
    "Schulden": False,
    "Wachstum": True,
}


# ------------------------------------------------------------
# Daten laden (wird 24 Stunden zwischengespeichert)
# ------------------------------------------------------------
def bilanz_kennzahlen(tk):
    try:
        gv = tk.income_stmt
        gewinne = gv.loc["Net Income"].dropna()
        umsatz = gv.loc["Total Revenue"].dropna()
    except Exception:
        return None, None
    if len(gewinne) < 3:
        schwankung = None
    elif (gewinne <= 0).any():
        schwankung = 99.0                      # Verlustjahr = sehr instabil
    else:
        schwankung = gewinne.std() / gewinne.mean()
    if len(umsatz) >= 3 and umsatz.iloc[-1] > 0:
        n = len(umsatz) - 1
        wachstum = (umsatz.iloc[0] / umsatz.iloc[-1]) ** (1 / n) - 1
    else:
        wachstum = None
    return schwankung, wachstum


@st.cache_data(ttl=60 * 60 * 24, show_spinner=False)
def lade_aktien():
    zeilen = []
    for region, liste in REGIONEN.items():
        for t in liste:
            try:
                tk = yf.Ticker(t)
                info = tk.info
                kurs = tk.history(period="1y")["Close"]
                schwankung, wachstum = bilanz_kennzahlen(tk)
                fcf, umsatz = info.get("freeCashflow"), info.get("totalRevenue")
                zeilen.append({
                    "Aktie": t,
                    "Name": info.get("shortName"),
                    "Region": region,
                    "Schwankung": schwankung,
                    "Marge": info.get("profitMargins"),
                    "ROE": info.get("returnOnEquity"),
                    "FCF-Marge": fcf / umsatz if fcf and umsatz else None,
                    "Schulden": info.get("debtToEquity"),
                    "Wachstum": wachstum,
                    "Dip %": round((kurs.iloc[-1] / kurs.max() - 1) * 100, 1),
                    "KGV": info.get("forwardPE"),
                })
            except Exception:
                pass
    return pd.DataFrame(zeilen)


def bereinigen(kurs):
    """Entfernt Datenfehler von Yahoo: Ein Welt-ETF kann nicht an einem Tag
    um mehr als 20 % springen. Solche Sprünge werden auf 0 % gesetzt und der
    Kurs aus den übrigen Tagesrenditen neu aufgebaut."""
    rendite = kurs.pct_change().fillna(0)
    rendite[rendite.abs() > 0.20] = 0
    neu = (1 + rendite).cumprod()
    return neu / neu.iloc[-1] * kurs.iloc[-1]   # heutiger Kurs bleibt gleich


@st.cache_data(ttl=60 * 60, show_spinner=False)
def lade_welt():
    kurs = yf.Ticker("SPYI.DE").history(period="max")["Close"]   # MSCI ACWI IMI, ganze Historie
    return bereinigen(kurs.dropna())


@st.cache_data(ttl=60 * 60, show_spinner=False)
def lade_markt():
    vix = yf.Ticker("^VIX").history(period="5d")["Close"].iloc[-1]
    welt = lade_welt()
    welt_dd = welt.iloc[-1] / welt.max() - 1    # Abstand zum Allzeithoch
    return vix, welt_dd


@st.cache_data(ttl=60 * 60 * 24, show_spinner=False)
def lade_kurs(t):
    return yf.Ticker(t).history(period="5y")["Close"]


# ------------------------------------------------------------
# Seitenleiste: Gewichte und Filter
# ------------------------------------------------------------
st.sidebar.header("⚖️ Gewichte des Ultrascores")
gewichte = {
    "Schwankung": st.sidebar.slider("Gewinnstabilität", 0, 50, 15, step=5),
    "Marge": st.sidebar.slider("Gewinnmarge", 0, 50, 35, step=5),
    "ROE": st.sidebar.slider("ROE (Eigenkapitalrendite)", 0, 50, 20, step=5),
    "FCF-Marge": st.sidebar.slider("Free-Cashflow-Marge", 0, 50, 10, step=5),
    "Schulden": st.sidebar.slider("Niedrige Verschuldung", 0, 50, 10, step=5),
    "Wachstum": st.sidebar.slider("Umsatzwachstum", 0, 50, 10, step=5),
}
summe = sum(gewichte.values())
st.sidebar.caption(f"Summe: {summe} % (wird automatisch auf 100 % umgerechnet)")

st.sidebar.header("🌍 Regionen")
regionen = st.sidebar.multiselect("Anzeigen", list(REGIONEN), default=list(REGIONEN))

# ------------------------------------------------------------
# Hauptseite
# ------------------------------------------------------------
st.title("📈 Ultrascore Screener")
st.caption("Bewertet die Stärke von 80 großen Unternehmen weltweit. "
           "Kein Anlagerat – nur ein Werkzeug zur eigenen Analyse.")

# Marktampel
try:
    vix, welt_dd = lade_markt()
    c1, c2, c3 = st.columns(3)
    c1.metric("VIX (Angst-Index)", f"{vix:.1f}")
    c2.metric("MSCI ACWI IMI unter Allzeithoch", f"{welt_dd * 100:.1f} %")
    if vix > 17.4 or welt_dd < -0.07:
        c3.error("🔴 Angstphase – Screener ist scharf!")
    else:
        c3.success("🟢 Keine Angstphase – beobachten")
except Exception:
    st.warning("Marktdaten konnten gerade nicht geladen werden.")

# MSCI ACWI IMI mit EMA 100 und Linien unter dem Allzeithoch
st.subheader("🌍 MSCI ACWI IMI – Einstiegszonen")
try:
    welt_voll = lade_welt()
    # Erst auf der ganzen Historie rechnen, damit EMA und Allzeithoch korrekt sind
    ema100 = welt_voll.ewm(span=100, adjust=False).mean()
    ath = welt_voll.cummax()                 # Allzeithoch bis zu jedem Tag
    linie_5 = ath * 0.97                     # 3 % unter dem Allzeithoch
    linie_75 = ath * 0.92                  # 8 % unter dem Allzeithoch

    zeitraum = st.radio("Zeitraum", ["1 Jahr", "3 Jahre", "5 Jahre", "Max"],
                        index=1, horizontal=True)
    jahre = {"1 Jahr": 1, "3 Jahre": 3, "5 Jahre": 5}.get(zeitraum)
    start = welt_voll.index[-1] - pd.DateOffset(years=jahre) if jahre else welt_voll.index[0]
    ab = welt_voll.index >= start

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=welt_voll.index[ab], y=welt_voll[ab], name="MSCI ACWI IMI",
                             line=dict(color="#9ca3af", width=1.5)))
    fig.add_trace(go.Scatter(x=welt_voll.index[ab], y=ema100[ab], name="EMA 100",
                             line=dict(color="#facc15", width=2)))
    fig.add_trace(go.Scatter(x=welt_voll.index[ab], y=linie_5[ab], name="−3 % unter Allzeithoch",
                             line=dict(color="#2563eb", width=1.5)))
    fig.add_trace(go.Scatter(x=welt_voll.index[ab], y=linie_75[ab], name="−8 % unter Allzeithoch",
                             line=dict(color="#7dd3fc", width=1.5)))
    fig.update_layout(height=450, hovermode="x unified",
                      margin=dict(l=0, r=0, t=30, b=0),
                      legend=dict(orientation="h", y=1.1))
    st.plotly_chart(fig)

    kurs_jetzt = welt_voll.iloc[-1]
    c1, c2, c3 = st.columns(3)
    c1.metric("Abstand zum Allzeithoch", f"{(kurs_jetzt / ath.iloc[-1] - 1) * 100:.1f} %")
    c2.metric("Abstand zur EMA 100", f"{(kurs_jetzt / ema100.iloc[-1] - 1) * 100:.1f} %")
    if kurs_jetzt < linie_75.iloc[-1]:
        c3.error("Unter der 8 %-Linie")
    elif kurs_jetzt < linie_5.iloc[-1]:
        c3.warning("Unter der 3 %-Linie")
    else:
        c3.success("Über beiden Linien")
except Exception:
    st.warning("Der MSCI-ACWI-IMI-Chart konnte gerade nicht geladen werden.")

# Aktiendaten
with st.spinner("Lade Daten für 80 Aktien … beim ersten Mal dauert das 3–5 Minuten."):
    df = lade_aktien()

if df.empty:
    st.error("Keine Daten geladen. Yahoo blockt vielleicht gerade – später nochmal versuchen.")
    st.stop()

# Ultrascore berechnen (auf allen Aktien, damit die Punkte vergleichbar bleiben)
df["U"] = 0.0
if summe > 0:
    for spalte, gewicht in gewichte.items():
        punkte = df[spalte].rank(ascending=RICHTUNG[spalte], pct=True).fillna(0.5)
        df["U"] += gewicht / summe * punkte
df["U"] = (df["U"] * 100).round(1)

# Anzeige-Spalten in Prozent
df["Marge %"] = (df["Marge"] * 100).round(1)
df["ROE %"] = (df["ROE"] * 100).round(1)
df["Wachstum %"] = (df["Wachstum"] * 100).round(1)

anzeige = df[df["Region"].isin(regionen)].sort_values("U", ascending=False)

st.subheader(f"🏆 Rangliste ({len(anzeige)} von {len(df)} Aktien)")
st.dataframe(
    anzeige[["Aktie", "Name", "Region", "U", "Marge %", "ROE %", "Wachstum %", "Dip %", "KGV"]],
    hide_index=True,
    column_config={
        "U": st.column_config.ProgressColumn("Ultrascore", min_value=0, max_value=100, format="%.1f"),
        "KGV": st.column_config.NumberColumn("Forward-KGV", format="%.1f"),
    },
)

# Detailansicht
st.subheader("🔍 Detailansicht")
if not anzeige.empty:
    auswahl = st.selectbox(
        "Aktie auswählen",
        anzeige["Aktie"] + " – " + anzeige["Name"].fillna(""),
    )
    ticker = auswahl.split(" – ")[0]
    kurs = lade_kurs(ticker)
    if not kurs.empty:
        drawdown = (kurs / kurs.cummax() - 1) * 100
        c1, c2 = st.columns(2)
        c1.markdown("**Kurs (5 Jahre)**")
        c1.line_chart(kurs)
        c2.markdown("**Abstand zum Hoch in %**")
        c2.area_chart(drawdown)
