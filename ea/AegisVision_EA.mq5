//+------------------------------------------------------------------+
//|                        AegisVision Trading EA                   |
//|         Multi-Timeframe Sliding Window + Swappable Trigger      |
//+------------------------------------------------------------------+
#property copyright "AegisVision"
#property version   "5.20"

#include <Trade\Trade.mqh>

// --- Custom enums for the standalone-mode inputs below ---
enum ENUM_RISK_MODE
{
    RISK_FIXED_LOT,        // Fixed lot size (LotSize input)
    RISK_PERCENT_BALANCE,  // Risk RiskPercent% of account balance per trade
    RISK_PERCENT_EQUITY    // Risk RiskPercent% of account equity per trade
};

enum ENUM_TP_MODE
{
    TP_NEAREST_SWING,  // Nearest 5m/1h swing high/low (liquidity pool) - mirrors the Python-side Agent 1 target
    TP_FIXED_RR        // Fixed multiple of the stop distance (FixedRiskRewardMultiple)
};

// Input parameters - grouped by what they actually govern (see each
// "input group" header). Groups collapse individually in MT5's EA
// properties dialog, so related knobs stay together on screen, not just
// in source order.

input group "=== Connection & Mode ==="
// BypassLLM is the master switch: true = standalone (no server contact,
// safe/fast for MT5's native Strategy Tester, trades directly off
// CheckStrategyTrigger() using the standalone SL/TP/risk inputs below).
// false = contacts the Python server, which applies the vision-compliance
// filter + guardrails before trading. Same trigger logic either way, so a
// strategy tuned in standalone mode carries over once this is flipped off.
input bool      BypassLLM = false;                 // Trade directly off the trigger (MT5 Strategy Tester mode) - no server contact
input string    PythonServerURL = "http://127.0.0.1:8080/analyze";  // Python server URL (ignored when BypassLLM = true)
input int       WebRequestTimeout = 30000;         // Web request timeout in milliseconds (ignored when BypassLLM = true)
input bool      EnableTrading = false;             // Enable actual trading (start with false!)
input int       MagicNumber = 12345;               // Magic number for trades

input group "=== Liveness Heartbeat (server mode only) ==="
// Independent of the trigger/analyze path - a tiny ping sent on a fixed
// timer (not tied to ticks or bar closes) so the GUI can show "EA
// connected" and live open-position P&L even during the long stretches
// between real trade evaluations. Never calls the LLM.
input string    HeartbeatURL = "http://127.0.0.1:8080/heartbeat";  // Heartbeat endpoint (ignored when BypassLLM = true)
input int       HeartbeatIntervalSeconds = 10;     // How often to send the heartbeat

input group "=== Bulk Historical Data (server mode only) ==="
input bool      EnableBulkLoad = true;             // Enable bulk historical data loading (ignored when BypassLLM = true)
input int       BulkLoad1MinCount = 360;           // 6 hours of 1-min candles
input int       BulkLoad5MinCount = 288;           // 24 hours of 5-min candles
input int       BulkLoad1HourCount = 48;           // 48 hours of 1-hour candles

input group "=== Trade Management Feedback (server mode only) ==="
input bool      EnableTradeManagement = true;      // Enable trade management suggestions (ignored when BypassLLM = true)

input group "=== Risk & Trade Limits ==="
input ENUM_RISK_MODE RiskMode = RISK_FIXED_LOT;    // How LotSize/RiskPercent translate into an actual lot size
input double    LotSize = 0.01;                    // Trade lot size (used when RiskMode = RISK_FIXED_LOT)
input double    RiskPercent = 1.0;                 // % of balance/equity risked per trade (used when RiskMode != RISK_FIXED_LOT)
input int       MaxSimultaneousTrades = 2;         // Maximum number of simultaneous trades (both modes)

input group "=== Strategy Trigger: MA & Slope ==="
input ENUM_MA_METHOD    MA_Method = MODE_SMA;         // Moving average type (SMA/EMA/SMMA/LWMA) - the trend/slope line
input int               MA_Period = 20;               // MA period (1-minute chart)
input ENUM_APPLIED_PRICE MA_AppliedPrice = PRICE_CLOSE; // Price series the MA is calculated from
input int       SlopeLookbackBars = 15;            // Bars back used to measure the MA slope
input double    MinSlopePoints = 30.0;             // Minimum |slope| (in raw broker points/bar, from the window's swing high/low to now) to call the MA "sharply angled" - tune on demo
input bool      DebugPrintSlope = false;           // Print the swing window's extreme bar/value and resulting slope every time the slope gate runs (verbose - for diagnosing slope discrepancies)

input group "=== Strategy Trigger: Touch & Confirmation ==="
input int       MaxConfirmationBars = 2;           // Touch candle itself, or up to this many bars after, may confirm
input double    MinBodyPercentOfRange = 40.0;      // Confirmation candle's body must be at least this % of its range (rejects dojis)

input group "=== Stop-Loss (standalone mode) ==="
// SL is placed at the swing high/low of the last SL_LookbackBars closed
// candles (the wick the price would have to reverse back through to
// invalidate the setup), plus a fixed points buffer beyond it.
input int       SL_LookbackBars = 3;               // Bars back searched for the SL swing high/low
input double    SL_BufferPoints = 100.0;           // Buffer beyond that swing high/low, in raw broker points

input group "=== Take-Profit & Risk:Reward (standalone mode) ==="
input ENUM_TP_MODE TakeProfitMode = TP_NEAREST_SWING; // How the take-profit level is chosen
input int       SwingLookbackBars = 50;            // Bars back (per timeframe) searched for a swing-high/low target
input int       SwingExcludeRecentBars = 3;        // Ignore this many most-recent bars when searching for a swing target (too close to be a real target)
input double    FixedRiskRewardMultiple = 2.0;     // Used when TakeProfitMode = TP_FIXED_RR
input double    MinRiskReward = 1.5;               // Skip the trade if the computed R:R is below this

// Global variables
CTrade trade;
string connectionId = "";
bool isInitialLoadComplete = false;
int maHandle = INVALID_HANDLE;

// Bar-close tracking, one timestamp per tier - drives the send cadence (a
// timeframe's candle is only sent when that timeframe actually closes a new
// bar, not on a fixed timer offset from EA-attach time).
datetime lastBarTimeM1 = 0;
datetime lastBarTimeM5 = 0;
datetime lastBarTimeH1 = 0;

// Pending "touch" state for the trigger state machine - a touch of the MA
// opens a short window (MaxConfirmationBars) during which a confirming close
// beyond the MA in the trend direction fires the signal.
bool     pendingTouch = false;
string   pendingDirection = "";
int      pendingBarsWaited = 0;

//+------------------------------------------------------------------+
//| Expert initialization function                                   |
//+------------------------------------------------------------------+
int OnInit()
{
    // Set trade parameters
    trade.SetExpertMagicNumber(MagicNumber);
    trade.SetDeviationInPoints(10);

    // Generate unique connection ID
    connectionId = "EA_" + Symbol() + "_" + IntegerToString(AccountInfoInteger(ACCOUNT_LOGIN)) + "_" + IntegerToString(GetTickCount());

    // Trend/slope MA on the 1-minute chart - type/period/price all configurable
    maHandle = iMA(_Symbol, PERIOD_M1, MA_Period, 0, MA_Method, MA_AppliedPrice);
    if(maHandle == INVALID_HANDLE)
    {
        Print("ERROR: Failed to create MA indicator handle: ", GetLastError());
        return(INIT_FAILED);
    }

    Print("LLM Trading EA with Sliding Window v5.0 initialized");
    Print("Python Server URL: ", PythonServerURL);
    Print("Heartbeat URL: ", HeartbeatURL, " (every ", HeartbeatIntervalSeconds, "s)");
    Print("Trading Enabled: ", EnableTrading ? "YES" : "NO");
    Print("Mode: ", BypassLLM ? "STANDALONE (no server contact - MT5 Strategy Tester)" : "LLM-filtered (contacts Python server)");
    // ... rest of init

    // Add the URL to allowed URLs for WebRequest
    string baseURL = "http://127.0.0.1:8080";
    if(!BypassLLM && !TerminalInfoInteger(TERMINAL_DLLS_ALLOWED))
    {
        Print("WARNING: DLL imports not allowed. Enable in EA settings.");
    }

    // Perform initial bulk load if enabled - skipped entirely in standalone mode,
    // which never talks to the Python server at all (this is what makes it safe
    // and fast to run in MT5's native Strategy Tester).
    if(EnableBulkLoad && !BypassLLM)
    {
        Print("Starting initial bulk data load...");
        if(SendBulkHistoricalData())
        {
            Print("Bulk data load completed successfully");
            isInitialLoadComplete = true;
        }
        else
        {
            Print("ERROR: Bulk data load failed, will try again later");
            isInitialLoadComplete = false;
        }
    }
    else
    {
        isInitialLoadComplete = true; // Skip bulk load
    }

    // Heartbeat runs on its own timer, not off ticks/bar-closes, so it keeps
    // firing even on a quiet symbol with no price movement - that's the
    // whole point of it as a liveness signal. No server to ping in
    // standalone mode.
    if(!BypassLLM)
        EventSetTimer(HeartbeatIntervalSeconds);

    return(INIT_SUCCEEDED);
}

//+------------------------------------------------------------------+
//| Expert deinitialization function                                |
//+------------------------------------------------------------------+
void OnDeinit(const int reason)
{
    EventKillTimer();
    if(!BypassLLM)
        SendDisconnectSignal();
    if(maHandle != INVALID_HANDLE)
        IndicatorRelease(maHandle);
    Print("LLM Trading EA with Sliding Window v5.0 deinitialized");
    Print("Connection ID was: ", connectionId);
}

//+------------------------------------------------------------------+
//| Timer tick - sends the liveness/open-positions heartbeat         |
//+------------------------------------------------------------------+
void OnTimer()
{
    if(BypassLLM)
        return;
    SendHeartbeat();
}

//+------------------------------------------------------------------+
//| Slope from the relevant swing extremum (trough for BUY, peak for |
//| SELL) within the last SlopeLookbackBars closed bars, to the      |
//| latest closed bar - i.e. how steep the MA's move into "now" has  |
//| been. Direction is a known input here (from touch-side context,  |
//| see CheckStrategyTrigger below), not derived from the slope      |
//| itself - so this only ever looks for the one extremum that       |
//| matters for that direction, not both.                            |
//|                                                                   |
//| Returns 0.0 if the current bar itself IS the extreme (no leg to  |
//| measure yet) - callers compare the result against MinSlopePoints |
//| so a 0.0 simply fails that check.                                |
//+------------------------------------------------------------------+
double GetSlopeToNow(string direction)
{
    int count = SlopeLookbackBars + 1;
    double maBuf[];
    ArraySetAsSeries(maBuf, true);
    if(CopyBuffer(maHandle, 0, 1, count, maBuf) <= 0) return 0.0;
    // maBuf[0] = latest closed bar (shift 1); maBuf[i] = i bars before that.

    int extremeIdx = 0;
    for(int i = 1; i < count; i++)
    {
        if(direction == "BUY")
        {
            if(maBuf[i] < maBuf[extremeIdx]) extremeIdx = i; // trough
        }
        else
        {
            if(maBuf[i] > maBuf[extremeIdx]) extremeIdx = i; // peak
        }
    }

    // "now" IS the extreme - no leg to measure yet
    double slope = (extremeIdx > 0) ? (maBuf[0] - maBuf[extremeIdx]) / extremeIdx / _Point : 0.0;

    if(DebugPrintSlope)
    {
        string dump = "";
        int copied = ArraySize(maBuf);
        for(int i = 0; i < copied; i++)
            dump += StringFormat("  [%d bars back] %s%s\n", i, DoubleToString(maBuf[i], _Digits), (i == extremeIdx ? "  <-- extreme" : ""));
        Print("=== SLOPE DEBUG (", direction, ", ", copied, " bars) ===\n", dump,
              "extreme=", extremeIdx, " bars back | now(0)=", DoubleToString(maBuf[0], _Digits),
              " | slope=", DoubleToString(slope, 2), " points | MinSlopePoints=", DoubleToString(MinSlopePoints, 2));
    }

    return slope;
}

//+------------------------------------------------------------------+
//| STRATEGY TRIGGER: MA touch/rejection pullback continuation.      |
//|                                                                   |
//| 1. Touch-side context: which side of the MA did this candle      |
//|    approach from? open > MA and low <= MA = an uptrend-side      |
//|    ("BUY") touch; open < MA and high >= MA = a downtrend-side    |
//|    ("SELL") touch. Purely positional - slope plays no role here, |
//|    so a single bearish candle dipping down from above an uptrend |
//|    can never be mistaken for a fresh SELL context.                |
//| 2. First confirmation: a candle of the opposite color to the     |
//|    touch's failure mode (bullish for a BUY touch, bearish for a  |
//|    SELL touch) closes back on the trend side of the MA, with a  |
//|    real body (MinBodyPercentOfRange) - same bar as the touch, or |
//|    any of the next MaxConfirmationBars bars. A same-colored      |
//|    candle failing to reclaim the MA never counts, no matter how  |
//|    long it keeps happening - it just leaves the window open (or  |
//|    lets it expire).                                              |
//| 3. Slope gate: evaluated exactly once, at the bar that supplies  |
//|    first confirmation (not cached from the touch bar) - the      |
//|    steepness from the window's swing extremum to THIS bar must   |
//|    clear MinSlopePoints. If it doesn't, the cycle is rejected     |
//|    outright (no trade) and the EA returns to idle, even if bars   |
//|    remain in the confirmation window.                            |
//|                                                                   |
//| Once a touch is pending, direction stays locked to               |
//| pendingDirection for the whole window - it is never re-derived   |
//| bar-to-bar while pending.                                        |
//|                                                                   |
//| Called once per closed 1-minute bar (see OnTick). Swap this      |
//| function's body for a different setup later - everything         |
//| downstream (data collection, agent pipeline, guardrails, order   |
//| execution) only depends on it returning a direction + slope.     |
//+------------------------------------------------------------------+
bool CheckStrategyTrigger(string &outDirection, double &outSlope)
{
    double maAtClose[];
    if(CopyBuffer(maHandle, 0, 1, 1, maAtClose) <= 0) return false;
    double maValue = maAtClose[0];

    MqlRates closedBar[];
    if(CopyRates(_Symbol, PERIOD_M1, 1, 1, closedBar) <= 0) return false;

    double bodySize = MathAbs(closedBar[0].close - closedBar[0].open);
    double rangeSize = closedBar[0].high - closedBar[0].low;
    bool strongBody = (rangeSize > 0) && (bodySize / rangeSize * 100.0 >= MinBodyPercentOfRange);
    bool isBullish = closedBar[0].close > closedBar[0].open;
    bool isBearish = closedBar[0].close < closedBar[0].open;

    if(pendingTouch)
    {
        pendingBarsWaited++;

        bool firstConfirmNow = strongBody && ((pendingDirection == "BUY")
            ? (isBullish && closedBar[0].close > maValue)
            : (isBearish && closedBar[0].close < maValue));

        if(firstConfirmNow)
        {
            double slope = GetSlopeToNow(pendingDirection);
            pendingTouch = false;
            bool slopeOk = (pendingDirection == "BUY") ? (slope >= MinSlopePoints) : (slope <= -MinSlopePoints);
            if(!slopeOk) return false; // confirmed color/close, but too shallow - reject, back to idle
            outDirection = pendingDirection;
            outSlope = slope;
            return true;
        }

        if(pendingBarsWaited > MaxConfirmationBars)
            pendingTouch = false; // window expired, no confirming candle appeared
        return false;
    }

    // Idle: direction comes only from which side of the MA this candle
    // approached from - no slope involved yet.
    bool buyTouch  = (closedBar[0].open > maValue) && (closedBar[0].low  <= maValue);
    bool sellTouch = (closedBar[0].open < maValue) && (closedBar[0].high >= maValue);
    if(!buyTouch && !sellTouch) return false;
    string touchDirection = buyTouch ? "BUY" : "SELL";

    bool firstConfirmNow = strongBody && ((touchDirection == "BUY")
        ? (isBullish && closedBar[0].close > maValue)
        : (isBearish && closedBar[0].close < maValue));

    if(firstConfirmNow)
    {
        // Touch and first confirmation landed on the same bar
        double slope = GetSlopeToNow(touchDirection);
        bool slopeOk = (touchDirection == "BUY") ? (slope >= MinSlopePoints) : (slope <= -MinSlopePoints);
        if(!slopeOk) return false; // confirmed color/close, but too shallow - reject
        outDirection = touchDirection;
        outSlope = slope;
        return true;
    }

    pendingTouch = true;
    pendingDirection = touchDirection;
    pendingBarsWaited = 0;
    return false;
}

//+------------------------------------------------------------------+
//| Expert tick function                                             |
//+------------------------------------------------------------------+
void OnTick()
{
    // Check if initial bulk load is complete
    if(EnableBulkLoad && !isInitialLoadComplete)
    {
        // Try bulk load again every 60 seconds
        static datetime lastBulkLoadAttempt = 0;
        if(TimeCurrent() - lastBulkLoadAttempt >= 60)
        {
            Print("Retrying bulk data load...");
            if(SendBulkHistoricalData())
            {
                Print("Bulk data load completed successfully on retry");
                isInitialLoadComplete = true;
            }
            lastBulkLoadAttempt = TimeCurrent();
        }
        return; // Don't proceed until bulk load is complete
    }

    // Detect new-bar-close events per tier. M5/H1 boundaries always land on an
    // M1 boundary too (5 and 60 are multiples of 1), so a single check driven
    // off the M1 close covers all three tiers - no separate polling needed.
    datetime curM1 = iTime(_Symbol, PERIOD_M1, 0);
    datetime curM5 = iTime(_Symbol, PERIOD_M5, 0);
    datetime curH1 = iTime(_Symbol, PERIOD_H1, 0);

    bool firstTick = (lastBarTimeM1 == 0);
    bool newM1 = !firstTick && (curM1 != lastBarTimeM1);
    bool newM5 = !firstTick && (curM5 != lastBarTimeM5);
    bool newH1 = !firstTick && (curH1 != lastBarTimeH1);

    lastBarTimeM1 = curM1;
    lastBarTimeM5 = curM5;
    lastBarTimeH1 = curH1;

    if(firstTick || !newM1)
        return; // only act right at a 1-minute bar close

    // 1. Routine keep-alive update: send whichever tier(s) just closed a bar.
    // This is a tiny payload (a few floats per candle) sent once a minute at
    // most - it keeps the server-side sliding windows current even when no
    // signal fires, but it never calls the LLM (see trading_server.py's
    // "candle_close" vs "signal" dispatch), so it costs nothing beyond one
    // local HTTP round-trip per minute. Skipped entirely in standalone mode -
    // there is no server to update, and MT5's Strategy Tester shouldn't be
    // making network calls at all.
    if(!BypassLLM)
    {
        string updateJson = BuildCandleCloseUpdate(true, newM5, newH1);
        SendDataToPython(updateJson);
    }

    // 2. Strategy trigger check, evaluated on the just-closed 1-minute bar.
    string direction = "";
    double slope = 0.0;
    if(CheckStrategyTrigger(direction, slope))
    {
        if(BypassLLM)
        {
            // Standalone mode: no server, no vision filter - trade directly off
            // the mechanical trigger so it can be refined/backtested in MT5's
            // native Strategy Tester.
            ExecuteStandaloneTrade(direction, slope);
        }
        else
        {
            string signalJson = BuildSignalPayload(direction, slope);
            string signal = SendDataToPython(signalJson);
            if(signal != "")
                ProcessTradingSignal(signal);
        }
    }
}

//+------------------------------------------------------------------+
//| Send bulk historical data for sliding window initialization     |
//+------------------------------------------------------------------+
bool SendBulkHistoricalData()
{
    Print("Preparing bulk historical data...");

    // Get 1-minute candles (ultra-short-term tier)
    MqlRates rates1min[];
    int copied1min = CopyRates(_Symbol, PERIOD_M1, 0, BulkLoad1MinCount, rates1min);
    if(copied1min <= 0)
    {
        Print("Error copying 1-minute rates: ", GetLastError());
        return false;
    }

    // Get 5-minute candles
    MqlRates rates5min[];
    int copied5min = CopyRates(_Symbol, PERIOD_M5, 0, BulkLoad5MinCount, rates5min);
    if(copied5min <= 0)
    {
        Print("Error copying 5-minute rates: ", GetLastError());
        return false;
    }

    // Get 1-hour candles
    MqlRates rates1hour[];
    int copied1hour = CopyRates(_Symbol, PERIOD_H1, 0, BulkLoad1HourCount, rates1hour);
    if(copied1hour <= 0)
    {
        Print("Error copying 1-hour rates: ", GetLastError());
        return false;
    }

    Print("Copied ", copied1min, " 1-minute, ", copied5min, " 5-minute, and ", copied1hour, " 1-hour candles");

    // Prepare JSON for bulk load
    string json = "{";
    json += "\"request_type\":\"bulk_load\",";
    json += "\"symbol\":\"" + _Symbol + "\",";
    json += "\"connection_id\":\"" + connectionId + "\",";

    // Add 1-minute candles
    json += "\"candles_1min\":[";
    for(int i = 0; i < copied1min; i++)
    {
        if(i > 0) json += ",";
        json += FormatCandleJSON(rates1min[i], "M1", i);
    }
    json += "],";

    // Add 5-minute candles
    json += "\"candles_5min\":[";
    for(int i = 0; i < copied5min; i++)
    {
        if(i > 0) json += ",";
        json += FormatCandleJSON(rates5min[i], "M5", i);
    }
    json += "],";

    // Add 1-hour candles
    json += "\"candles_1hour\":[";
    for(int i = 0; i < copied1hour; i++)
    {
        if(i > 0) json += ",";
        json += FormatCandleJSON(rates1hour[i], "H1", i);
    }
    json += "]";
    json += "}";
    
    Print("Sending bulk data to Python server (", StringLen(json), " characters)...");
    
    // Send to Python server
    string result = SendDataToPython(json);
    
    if(result != "")
    {
        Print("Bulk data load response received");
        return true;
    }
    else
    {
        Print("ERROR: No response from bulk data load");
        return false;
    }
}

//+------------------------------------------------------------------+
//| Build the shared trailer (open trades / account state) appended  |
//| to every candle_close / signal payload.                          |
//+------------------------------------------------------------------+
string BuildAccountAndTradesTrailer()
{
    string json = "\"spread\":" + DoubleToString(SymbolInfoInteger(_Symbol, SYMBOL_SPREAD) / 10.0, 1) + ",";
    // Account equity/balance let the server-side guardrail track daily drawdown
    json += "\"account_balance\":" + DoubleToString(AccountInfoDouble(ACCOUNT_BALANCE), 2) + ",";
    json += "\"account_equity\":" + DoubleToString(AccountInfoDouble(ACCOUNT_EQUITY), 2);

    if(EnableTradeManagement)
    {
        json += "," + GetOpenTradesInfo();
        json += ",\"max_trades\":" + IntegerToString(MaxSimultaneousTrades);
        json += ",\"current_trade_count\":" + IntegerToString(CountOpenTrades());
    }
    return json;
}

//+------------------------------------------------------------------+
//| Routine keep-alive update: sent once per 1-minute bar close,     |
//| carrying only the tier(s) that actually just closed a bar (M1    |
//| always; M5/H1 only every 5th/60th minute). Ingested server-side  |
//| to keep the sliding windows current - never invokes the LLM      |
//| pipeline (see trading_server.py's "candle_close" handling).      |
//+------------------------------------------------------------------+
string BuildCandleCloseUpdate(bool includeM1, bool includeM5, bool includeH1)
{
    string json = "{";
    json += "\"request_type\":\"candle_close\",";
    json += "\"symbol\":\"" + _Symbol + "\",";
    json += "\"connection_id\":\"" + connectionId + "\",";

    json += "\"candles\":[";
    bool first = true;
    MqlRates r[];
    if(includeM1 && CopyRates(_Symbol, PERIOD_M1, 1, 1, r) > 0)
    {
        json += FormatCandleJSON(r[0], "M1", 1);
        first = false;
    }
    if(includeM5 && CopyRates(_Symbol, PERIOD_M5, 1, 1, r) > 0)
    {
        if(!first) json += ",";
        json += FormatCandleJSON(r[0], "M5", 1);
        first = false;
    }
    if(includeH1 && CopyRates(_Symbol, PERIOD_H1, 1, 1, r) > 0)
    {
        if(!first) json += ",";
        json += FormatCandleJSON(r[0], "H1", 1);
        first = false;
    }
    json += "],";

    json += BuildAccountAndTradesTrailer();
    json += "}";
    return json;
}

//+------------------------------------------------------------------+
//| Signal payload: sent only when CheckStrategyTrigger() fires.     |
//| Always carries the freshest M1/M5/H1 candle plus the trigger's   |
//| direction/slope, so the vision-compliance agent evaluates a      |
//| fully current multi-timeframe snapshot regardless of whether     |
//| M5/H1 happened to close on this exact minute.                    |
//+------------------------------------------------------------------+
string BuildSignalPayload(string direction, double slope)
{
    MqlRates rM1[], rM5[], rH1[];
    if(CopyRates(_Symbol, PERIOD_M1, 1, 1, rM1) <= 0) return "";
    if(CopyRates(_Symbol, PERIOD_M5, 0, 1, rM5) <= 0) return "";
    if(CopyRates(_Symbol, PERIOD_H1, 0, 1, rH1) <= 0) return "";

    string json = "{";
    json += "\"request_type\":\"signal\",";
    json += "\"symbol\":\"" + _Symbol + "\",";
    json += "\"connection_id\":\"" + connectionId + "\",";
    json += "\"trigger_direction\":\"" + direction + "\",";
    json += "\"trigger_slope_points\":" + DoubleToString(slope, 2) + ",";

    json += "\"candles\":[";
    json += FormatCandleJSON(rM1[0], "M1", 1) + ",";
    json += FormatCandleJSON(rM5[0], "M5", 0) + ",";
    json += FormatCandleJSON(rH1[0], "H1", 0);
    json += "],";

    json += BuildAccountAndTradesTrailer();
    json += "}";
    return json;
}

//+------------------------------------------------------------------+
//| Format candle data as JSON                                      |
//+------------------------------------------------------------------+
string FormatCandleJSON(const MqlRates &rate, string timeframe, int index)
{
    string json = "{";
    json += "\"timeframe\":\"" + timeframe + "\",";
    json += "\"timestamp\":\"" + TimeToString(rate.time, TIME_DATE|TIME_MINUTES|TIME_SECONDS) + "\",";
    json += "\"open_price\":" + DoubleToString(rate.open, _Digits) + ",";
    json += "\"high_price\":" + DoubleToString(rate.high, _Digits) + ",";
    json += "\"low_price\":" + DoubleToString(rate.low, _Digits) + ",";
    json += "\"close_price\":" + DoubleToString(rate.close, _Digits) + ",";
    json += "\"volume\":" + IntegerToString(rate.tick_volume);
    
    // Add technical indicators for recent candles (last 50 candles to save processing time)
    if(index < 50)
    {
        string indicators = GetTechnicalIndicatorsForCandle(timeframe, index);
        if(indicators != "")
        {
            json += "," + indicators;
        }
    }
    
    json += "}";
    return json;
}

//+------------------------------------------------------------------+
//| Get technical indicators for specific candle                    |
//+------------------------------------------------------------------+
string GetTechnicalIndicatorsForCandle(string timeframe, int index)
{
    ENUM_TIMEFRAMES tf = StringToTimeframe(timeframe);
    
    double rsiArray[];
    int rsi_handle = iRSI(_Symbol, tf, 14, PRICE_CLOSE);
    if(CopyBuffer(rsi_handle, 0, index, 1, rsiArray) > 0)
    {
        string json = "\"rsi\":" + DoubleToString(rsiArray[0], 2);
        
        // Add MACD
        double macdMain[], macdSignal[];
        int macd_handle = iMACD(_Symbol, tf, 12, 26, 9, PRICE_CLOSE);
        if(CopyBuffer(macd_handle, 0, index, 1, macdMain) > 0 && CopyBuffer(macd_handle, 1, index, 1, macdSignal) > 0)
        {
            json += ",\"macd\":" + DoubleToString(macdMain[0], 5);
            json += ",\"macd_signal\":" + DoubleToString(macdSignal[0], 5);
            json += ",\"macd_histogram\":" + DoubleToString(macdMain[0] - macdSignal[0], 5);
        }
        
        // Add Bollinger Bands
        double bbUpper[], bbMiddle[], bbLower[];
        int bb_handle = iBands(_Symbol, tf, 20, 0, 2, PRICE_CLOSE);
        if(CopyBuffer(bb_handle, 1, index, 1, bbUpper) > 0 && 
           CopyBuffer(bb_handle, 0, index, 1, bbMiddle) > 0 && 
           CopyBuffer(bb_handle, 2, index, 1, bbLower) > 0)
        {
            json += ",\"bb_upper\":" + DoubleToString(bbUpper[0], _Digits);
            json += ",\"bb_middle\":" + DoubleToString(bbMiddle[0], _Digits);
            json += ",\"bb_lower\":" + DoubleToString(bbLower[0], _Digits);
        }
        
        // Add Moving Averages
        double ma5[], ma20[], ma50[];
        int ma5_handle = iMA(_Symbol, tf, 5, 0, MODE_SMA, PRICE_CLOSE);
        int ma20_handle = iMA(_Symbol, tf, 20, 0, MODE_SMA, PRICE_CLOSE);
        int ma50_handle = iMA(_Symbol, tf, 50, 0, MODE_SMA, PRICE_CLOSE);
        
        if(CopyBuffer(ma5_handle, 0, index, 1, ma5) > 0)
            json += ",\"ma_5\":" + DoubleToString(ma5[0], _Digits);
        if(CopyBuffer(ma20_handle, 0, index, 1, ma20) > 0)
            json += ",\"ma_20\":" + DoubleToString(ma20[0], _Digits);
        if(CopyBuffer(ma50_handle, 0, index, 1, ma50) > 0)
            json += ",\"ma_50\":" + DoubleToString(ma50[0], _Digits);
        
        // Add OBV (On Balance Volume)
        double obvArray[];
        int obv_handle = iOBV(_Symbol, tf, VOLUME_TICK);
        if(CopyBuffer(obv_handle, 0, index, 1, obvArray) > 0)
            json += ",\"obv\":" + DoubleToString(obvArray[0], 0);
        
        // Add ATR (Average True Range)
        double atrArray[];
        int atr_handle = iATR(_Symbol, tf, 14);
        if(CopyBuffer(atr_handle, 0, index, 1, atrArray) > 0)
            json += ",\"atr\":" + DoubleToString(atrArray[0], _Digits);
        
        // Add ADX (Average Directional Index)
        double adxArray[];
        int adx_handle = iADX(_Symbol, tf, 14);
        if(CopyBuffer(adx_handle, 0, index, 1, adxArray) > 0)
            json += ",\"adx\":" + DoubleToString(adxArray[0], 2);
        
        return json;
    }
    
    return "";
}

//+------------------------------------------------------------------+
//| Convert timeframe string to enum                               |
//+------------------------------------------------------------------+
ENUM_TIMEFRAMES StringToTimeframe(string tf)
{
    if(tf == "M5") return PERIOD_M5;
    if(tf == "H1") return PERIOD_H1;
    if(tf == "M1") return PERIOD_M1;
    if(tf == "M15") return PERIOD_M15;
    if(tf == "M30") return PERIOD_M30;
    if(tf == "H4") return PERIOD_H4;
    if(tf == "D1") return PERIOD_D1;
    return _Period;
}

//+------------------------------------------------------------------+
//| Get timeframe string from enum                                  |
//+------------------------------------------------------------------+
string GetTimeframeString(ENUM_TIMEFRAMES tf)
{
    switch(tf)
    {
        case PERIOD_M1: return "M1";
        case PERIOD_M5: return "M5";
        case PERIOD_M15: return "M15";
        case PERIOD_M30: return "M30";
        case PERIOD_H1: return "H1";
        case PERIOD_H4: return "H4";
        case PERIOD_D1: return "D1";
        default: return "M5";
    }
}

//+------------------------------------------------------------------+
//| Send data to Python script using WebRequest                     |
//+------------------------------------------------------------------+
string SendDataToPython(string data)
{
    char postData[];
    char result[];
    string headers;
    
    // Convert JSON string to char array (without null terminator)
    // Convert JSON string to char array
    // We strictly resize the array to avoid sending extra null bytes or junk data
    int charCount = StringToCharArray(data, postData, 0, WHOLE_ARRAY, CP_UTF8);
    int dataLen = charCount - 1; // Exclude the null terminator
    
    if (dataLen > 0) {
        ArrayResize(postData, dataLen);
    } else {
        Print("Error: Failed to convert string to char array");
        return "";
    }
    
    // Set headers for JSON POST request
    headers = "Content-Type: application/json\r\n";
    
    Print("Sending data to Python server...");
    Print("Data length: ", dataLen, " bytes");
    
    // Send POST request
    int response = WebRequest(
        "POST",                    // Method
        PythonServerURL,          // URL
        headers,                  // Headers
        WebRequestTimeout,        // Timeout
        postData,                 // POST data
        result,                   // Result array
        headers                   // Response headers
    );
    
    if(response == -1)
    {
        int error = GetLastError();
        Print("WebRequest error: ", error);
        return "";
    }
    
    if(response != 200)
    {
        Print("HTTP error: ", response);
        return "";
    }
    
    // Convert result to string
    string responseStr = CharArrayToString(result, 0, WHOLE_ARRAY, CP_UTF8);
    Print("Response: ", responseStr);

    return responseStr;
}

//+------------------------------------------------------------------+
//| Send the liveness/open-positions heartbeat. Fire-and-forget on   |
//| purpose - unlike SendDataToPython(), this never logs the full    |
//| request/response every call (it fires every ~10s forever, so     |
//| that would flood the Experts log) and a failure here is not a    |
//| trading-relevant error, just a missed heartbeat.                 |
//+------------------------------------------------------------------+
void SendHeartbeat()
{
    string json = "{";
    json += "\"symbol\":\"" + _Symbol + "\",";
    json += "\"connection_id\":\"" + connectionId + "\",";
    json += GetOpenTradesInfo();
    json += "}";

    char postData[];
    char result[];
    string headers = "Content-Type: application/json\r\n";

    int charCount = StringToCharArray(json, postData, 0, WHOLE_ARRAY, CP_UTF8);
    int dataLen = charCount - 1;
    if(dataLen <= 0)
        return;
    ArrayResize(postData, dataLen);

    int response = WebRequest(
        "POST",
        HeartbeatURL,
        headers,
        WebRequestTimeout,
        postData,
        result,
        headers
    );

    if(response == -1)
    {
        static datetime lastHeartbeatErrorPrint = 0;
        if(TimeCurrent() - lastHeartbeatErrorPrint >= 60)
        {
            Print("Heartbeat WebRequest error: ", GetLastError(), " (suppressing repeats for 60s)");
            lastHeartbeatErrorPrint = TimeCurrent();
        }
    }
}

//+------------------------------------------------------------------+
//| One-shot "I'm going away" ping, sent from OnDeinit() so the GUI  |
//| shows "EA not connected" and clears any open-position snapshot   |
//| immediately instead of waiting up to HeartbeatIntervalSeconds*3  |
//| for the liveness heuristic to notice on its own. Short, fixed    |
//| timeout (not WebRequestTimeout) so EA removal/recompile never    |
//| hangs waiting on the network if the server is unreachable.       |
//+------------------------------------------------------------------+
void SendDisconnectSignal()
{
    string json = "{\"disconnected\":true,\"connection_id\":\"" + connectionId + "\"}";

    char postData[];
    char result[];
    string headers = "Content-Type: application/json\r\n";

    int charCount = StringToCharArray(json, postData, 0, WHOLE_ARRAY, CP_UTF8);
    int dataLen = charCount - 1;
    if(dataLen <= 0)
        return;
    ArrayResize(postData, dataLen);

    WebRequest("POST", HeartbeatURL, headers, 3000, postData, result, headers);
    // Result intentionally ignored - EA is unwinding either way.
}

//+------------------------------------------------------------------+
//| Process trading signal from Python                              |
//+------------------------------------------------------------------+
void ProcessTradingSignal(string signal)
{
    if(signal == "")
        return;
        
    // Parse JSON response (improved parsing)
    string action = ExtractJsonString(signal, "action");
    double confidence = StringToDouble(ExtractJsonValue(signal, "confidence"));
    string reasoning = ExtractJsonString(signal, "reasoning");
    
    Print("=== LLM TRADING SIGNAL ===");
    Print("Action: ", action);
    Print("Confidence: ", DoubleToString(confidence, 1), "%");
    Print("Reasoning: ", reasoning);
    Print("========================");
    
    if(!EnableTrading)
    {
        Print("Trading disabled - Signal received but not executed");
        return;
    }
    
    // 1. Process Trade Management (Positions Updates)
    if(EnableTradeManagement)
    {
        ProcessPositionSuggestions(signal);
    }
    
    // 2. Process New Trades
    if((action == "BUY" || action == "SELL") && confidence >= 70)
    {
        // Close opposite positions functionality is safer to be explicit
        CloseOppositePositions(action);
        
        if(!CanOpenNewTrade())
        {
            Print("🚫 Cannot open new trade - Max trades limit reached");
            return;
        }
        
        double price = 0;
        double sl = 0;
        double tp = 0;
        
        if(action == "BUY")
        {
            price = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
            // Default Fallback
            sl = price - 50 * _Point;
            tp = price + 100 * _Point;
        }
        else
        {
            price = SymbolInfoDouble(_Symbol, SYMBOL_BID);
            // Default Fallback
            sl = price + 50 * _Point;
            tp = price - 100 * _Point;
        }
        
        // Extract EXACT SL/TP from JSON (if available)
        double signalSL = StringToDouble(ExtractJsonValue(signal, "stop_loss"));
        double signalTP = StringToDouble(ExtractJsonValue(signal, "take_profit"));
        
        if(signalSL > 0) sl = signalSL;
        if(signalTP > 0) tp = signalTP;
        
        // Execute
        if(action == "BUY")
            trade.Buy(LotSize, _Symbol, price, sl, tp, "LLM BUY " + DoubleToString(confidence, 0) + "%");
        else
            trade.Sell(LotSize, _Symbol, price, sl, tp, "LLM SELL " + DoubleToString(confidence, 0) + "%");
    }
}

//+------------------------------------------------------------------+
//| Extract Value from JSON string (Simple Helper)                  |
//+------------------------------------------------------------------+
string ExtractJsonValue(string json, string key)
{
    string searchKey = "\"" + key + "\":";
    int startPos = StringFind(json, searchKey);
    if(startPos < 0) return "";
    
    startPos += StringLen(searchKey);
    
    // Skip whitespace
    while(startPos < StringLen(json) && StringGetCharacter(json, startPos) == ' ') startPos++;
    
    // Check if it's a string
    if(StringGetCharacter(json, startPos) == '\"')
    {
        startPos++; // Skip quote
        int endPos = StringFind(json, "\"", startPos);
        if(endPos > 0) return StringSubstr(json, startPos, endPos - startPos);
    }
    else
    {
        // It's a number or boolean or null
        int endPos = startPos;
        while(endPos < StringLen(json))
        {
            ushort c = StringGetCharacter(json, endPos);
            if(c == ',' || c == '}' || c == ']' || c == ' ' || c == '\n') break;
            endPos++;
        }
        return StringSubstr(json, startPos, endPos - startPos);
    }
    return "";
}

//+------------------------------------------------------------------+
//| Extract String Value from JSON string                           |
//+------------------------------------------------------------------+
string ExtractJsonString(string json, string key)
{
    // Same as ExtractJsonValue but assumes string result we want
    string val = ExtractJsonValue(json, key);
    return val;
}

//+------------------------------------------------------------------+
//| Process Position Suggestions from JSON                          |
//+------------------------------------------------------------------+
void ProcessPositionSuggestions(string json)
{
    // Simplified parsing of position_suggestions array
    // This is a naive implementation because MQL5 JSON parsing is hard without a library
    // We look for objects inside "position_suggestions": [ ... ]
    
    int startList = StringFind(json, "\"position_suggestions\":");
    if(startList < 0) return;
    
    startList = StringFind(json, "[", startList);
    if(startList < 0) return;
    
    int endList = FindMatchingBracket(json, startList);
    if(endList < 0) return;
    
    string listContent = StringSubstr(json, startList + 1, endList - startList - 1);
    
    // Loop through objects in the list
    int currentPos = 0;
    while(currentPos < StringLen(listContent))
    {
        int objStart = StringFind(listContent, "{", currentPos);
        if(objStart < 0) break;
        
        int objEnd = FindMatchingBracket(listContent, objStart);
        if(objEnd < 0) break;
        
        string objContent = StringSubstr(listContent, objStart, objEnd - objStart + 1);
        ApplyTradeSuggestion(objContent);
        
        currentPos = objEnd + 1;
    }
}

//+------------------------------------------------------------------+
//| Find matching closing bracket                                   |
//+------------------------------------------------------------------+
int FindMatchingBracket(string text, int startPos)
{
    int level = 0;
    for(int i = startPos; i < StringLen(text); i++)
    {
        ushort c = StringGetCharacter(text, i);
        if(c == '{' || c == '[') level++;
        if(c == '}' || c == ']') 
        {
            level--;
            if(level == 0) return i;
        }
    }
    return -1;
}

//+------------------------------------------------------------------+
//| Apply improvement to a specific trade                           |
//+------------------------------------------------------------------+
void ApplyTradeSuggestion(string suggestionJson)
{
    string tradeIdStr = ExtractJsonString(suggestionJson, "trade_id");
    string action = ExtractJsonString(suggestionJson, "action");
    
    if(tradeIdStr == "") return;
    
    ulong ticket = (ulong)StringToInteger(tradeIdStr);
    
    if(!PositionSelectByTicket(ticket))
    {
        Print("Trade suggestion for unknown/closed ticket: ", ticket);
        return;
    }
    
    Print("Processing suggestion for Ticket ", ticket, ": ", action);
    
    if(action == "CLOSE")
    {
        trade.PositionClose(ticket);
    }
    else if(action == "PARTIAL_CLOSE")
    {
        double percentage = StringToDouble(ExtractJsonValue(suggestionJson, "close_percentage"));
        if(percentage > 0)
        {
            double vol = PositionGetDouble(POSITION_VOLUME);
            double closeVol = NormalizeDouble(vol * (percentage / 100.0), 2);
            if(closeVol >= 0.01)
                trade.PositionClosePartial(ticket, closeVol);
        }
    }
    else if(action == "MOVE_SL_TO_BE" || action == "TRAIL_SL" || action == "HOLD")
    {
        // Update SL/TP if provided
        double newSL = -1;
        double newTP = -1;
        
        string valSL = ExtractJsonValue(suggestionJson, "new_sl");
        if(valSL != "" && valSL != "null") newSL = StringToDouble(valSL);
        
        string valTP = ExtractJsonValue(suggestionJson, "new_tp");
        if(valTP != "" && valTP != "null") newTP = StringToDouble(valTP);
        
        double currentSL = PositionGetDouble(POSITION_SL);
        double currentTP = PositionGetDouble(POSITION_TP);
        
        bool modify = false;
        
        if(newSL > 0 && MathAbs(newSL - currentSL) > _Point) modify = true;
        if(newTP > 0 && MathAbs(newTP - currentTP) > _Point) modify = true;
        
        if(modify)
        {
            if(newSL <= 0) newSL = currentSL;
            if(newTP <= 0) newTP = currentTP;
            
            trade.PositionModify(ticket, newSL, newTP);
            Print("Updated SL/TP for Ticket ", ticket);
        }
    }
}

//+------------------------------------------------------------------+
//| Close positions opposite to signal direction                    |
//+------------------------------------------------------------------+
void CloseOppositePositions(string signalAction)
{
    for(int i = PositionsTotal() - 1; i >= 0; i--)
    {
        string symbol = PositionGetSymbol(i);
        if(symbol == _Symbol && PositionGetInteger(POSITION_MAGIC) == MagicNumber)
        {
            ENUM_POSITION_TYPE posType = (ENUM_POSITION_TYPE)PositionGetInteger(POSITION_TYPE);
            
            bool shouldClose = false;
            if(signalAction == "BUY" && posType == POSITION_TYPE_SELL)
                shouldClose = true;
            else if(signalAction == "SELL" && posType == POSITION_TYPE_BUY)
                shouldClose = true;
            
            if(shouldClose)
            {
                ulong ticket = PositionGetInteger(POSITION_TICKET);
                if(trade.PositionClose(ticket))
                {
                    Print("🔄 Closed opposite position: ", ticket);
                }
            }
        }
    }
}

//+------------------------------------------------------------------+
//| Count open positions with this EA's magic number               |
//+------------------------------------------------------------------+
int CountOpenTrades()
{
    int count = 0;
    for(int i = PositionsTotal() - 1; i >= 0; i--)
    {
        string symbol = PositionGetSymbol(i);
        if(symbol == _Symbol)
        {
            if(PositionSelect(_Symbol))
            {
                if(PositionGetInteger(POSITION_MAGIC) == MagicNumber)
                {
                    count++;
                }
            }
        }
    }
    return count;
}

//+------------------------------------------------------------------+
//| Get open trades information as JSON string                      |
//+------------------------------------------------------------------+
string GetOpenTradesInfo()
{
    string tradesJson = "\"open_trades\":[";
    bool firstTrade = true;
    
    for(int i = PositionsTotal() - 1; i >= 0; i--)
    {
        string symbol = PositionGetSymbol(i);
        if(symbol == _Symbol)
        {
            if(PositionSelect(_Symbol))
            {
                if(PositionGetInteger(POSITION_MAGIC) == MagicNumber)
                {
                    if(!firstTrade) tradesJson += ",";
                    
                    ulong ticket = PositionGetInteger(POSITION_TICKET);
                    double openPrice = PositionGetDouble(POSITION_PRICE_OPEN);
                    double currentPrice = PositionGetDouble(POSITION_PRICE_CURRENT);
                    double volume = PositionGetDouble(POSITION_VOLUME);
                    double sl = PositionGetDouble(POSITION_SL);
                    double tp = PositionGetDouble(POSITION_TP);
                    ENUM_POSITION_TYPE type = (ENUM_POSITION_TYPE)PositionGetInteger(POSITION_TYPE);
                    datetime openTime = (datetime)PositionGetInteger(POSITION_TIME);
                    double profit = PositionGetDouble(POSITION_PROFIT);
                    double swap = PositionGetDouble(POSITION_SWAP);
                    
                    tradesJson += "{";
                    tradesJson += "\"ticket\":" + IntegerToString(ticket) + ",";
                    tradesJson += "\"type\":\"" + (type == POSITION_TYPE_BUY ? "BUY" : "SELL") + "\",";
                    tradesJson += "\"open_price\":" + DoubleToString(openPrice, _Digits) + ",";
                    tradesJson += "\"current_price\":" + DoubleToString(currentPrice, _Digits) + ",";
                    tradesJson += "\"volume\":" + DoubleToString(volume, 2) + ",";
                    tradesJson += "\"stop_loss\":" + DoubleToString(sl, _Digits) + ",";
                    tradesJson += "\"take_profit\":" + DoubleToString(tp, _Digits) + ",";
                    tradesJson += "\"open_time\":\"" + TimeToString(openTime) + "\",";
                    tradesJson += "\"profit\":" + DoubleToString(profit, 2) + ",";
                    tradesJson += "\"swap\":" + DoubleToString(swap, 2);
                    tradesJson += "}";
                    
                    firstTrade = false;
                }
            }
        }
    }
    
    tradesJson += "]";
    return tradesJson;
}

//+------------------------------------------------------------------+
//| Check if new trade is allowed based on max trades limit        |
//+------------------------------------------------------------------+
bool CanOpenNewTrade()
{
    int currentTrades = CountOpenTrades();
    return currentTrades < MaxSimultaneousTrades;
}

//+------------------------------------------------------------------+
//| STANDALONE MODE (BypassLLM = true): execute directly off the     |
//| mechanical trigger, computing SL/TP right here rather than        |
//| waiting on the Python pipeline. The SL/TP math intentionally      |
//| mirrors agents/ingestor.py's compute_trigger_metrics() (stop at   |
//| the recent swing extreme plus a points buffer, take-profit at     |
//| the nearest 5m/1h swing) so a strategy tuned here in MT5's        |
//| Strategy Tester behaves the same way once BypassLLM is switched   |
//| off.                                                               |
//+------------------------------------------------------------------+
void ExecuteStandaloneTrade(string direction, double slope)
{
    if(!EnableTrading)
    {
        Print("Standalone signal: ", direction, " (slope ", DoubleToString(slope, 2), " points) - trading disabled, not executed");
        return;
    }

    if(!CanOpenNewTrade())
    {
        Print("Standalone signal: max trades reached, skipping");
        return;
    }

    CloseOppositePositions(direction);

    double price = (direction == "BUY") ? SymbolInfoDouble(_Symbol, SYMBOL_ASK) : SymbolInfoDouble(_Symbol, SYMBOL_BID);

    double sl = ComputeStandaloneStopLoss(direction, price);
    double tp = ComputeStandaloneTakeProfit(direction, price, sl);

    double risk = MathAbs(price - sl);
    double reward = MathAbs(tp - price);
    if(risk <= 0 || (reward / risk) < MinRiskReward)
    {
        Print("Standalone signal: R:R ", DoubleToString(risk > 0 ? reward / risk : 0, 2),
              " below minimum ", DoubleToString(MinRiskReward, 2), " - skipping");
        return;
    }

    double lots = CalculateLotSize(risk);

    bool ok;
    string comment = "STANDALONE " + direction + " slope=" + DoubleToString(slope, 1);
    if(direction == "BUY")
        ok = trade.Buy(lots, _Symbol, price, sl, tp, comment);
    else
        ok = trade.Sell(lots, _Symbol, price, sl, tp, comment);

    if(ok)
        Print("Standalone trade executed: ", direction, " lots=", DoubleToString(lots, 2),
              " SL=", DoubleToString(sl, _Digits), " TP=", DoubleToString(tp, _Digits),
              " R:R=", DoubleToString(reward / risk, 2));
    else
        Print("Standalone trade FAILED: ", direction, " error=", GetLastError());
}

//+------------------------------------------------------------------+
//| Stop-loss: the swing high/low of the last SL_LookbackBars closed  |
//| 1-min candles - the wick price would have to break back through   |
//| to invalidate this setup (e.g. for a bearish entry: touch candle  |
//| was bullish, the confirming candle closed bearish below the MA -  |
//| the SL goes at the highest wick of that lookback window) - plus a |
//| fixed SL_BufferPoints buffer beyond it, in the counter-trend      |
//| direction.                                                        |
//+------------------------------------------------------------------+
double ComputeStandaloneStopLoss(string direction, double price)
{
    MqlRates recent[];
    int copied = CopyRates(_Symbol, PERIOD_M1, 1, SL_LookbackBars, recent);
    if(copied <= 0)
    {
        // Fallback if history is unavailable - a fixed 50-point stop rather than no stop at all
        return (direction == "BUY") ? price - 50 * _Point : price + 50 * _Point;
    }

    double buffer = SL_BufferPoints * _Point;

    if(direction == "BUY")
    {
        double extreme = recent[0].low;
        for(int i = 1; i < copied; i++) extreme = MathMin(extreme, recent[i].low);
        return extreme - buffer;
    }
    else
    {
        double extreme = recent[0].high;
        for(int i = 1; i < copied; i++) extreme = MathMax(extreme, recent[i].high);
        return extreme + buffer;
    }
}

//+------------------------------------------------------------------+
//| Take-profit: nearest 5m/1h swing high/low beyond current price    |
//| (TP_NEAREST_SWING), or a fixed R:R multiple of the stop distance  |
//| (TP_FIXED_RR).                                                    |
//+------------------------------------------------------------------+
double ComputeStandaloneTakeProfit(string direction, double price, double sl)
{
    if(TakeProfitMode == TP_NEAREST_SWING)
    {
        double swingTarget = FindNearestSwingTarget(direction, price);
        if(swingTarget > 0)
            return swingTarget;
        // No usable swing target found (not enough history) - fall back to the fixed multiple
    }

    double riskDist = MathAbs(price - sl);
    return (direction == "BUY") ? price + riskDist * FixedRiskRewardMultiple : price - riskDist * FixedRiskRewardMultiple;
}

//+------------------------------------------------------------------+
//| Nearest liquidity-pool candidate across the 5m and 1h timeframes: |
//| the closer of the two swing levels that's still beyond current    |
//| price in the trade direction. Mirrors ingestor.py's               |
//| _find_swing_target()/compute_trigger_metrics() candidate logic.   |
//+------------------------------------------------------------------+
double FindNearestSwingTarget(string direction, double price)
{
    double target5m = FindSwingOnTimeframe(PERIOD_M5, direction);
    double target1h = FindSwingOnTimeframe(PERIOD_H1, direction);

    double best = 0.0;
    bool haveBest = false;

    if(target5m > 0 && ((direction == "BUY" && target5m > price) || (direction == "SELL" && target5m < price)))
    {
        best = target5m;
        haveBest = true;
    }
    if(target1h > 0 && ((direction == "BUY" && target1h > price) || (direction == "SELL" && target1h < price)))
    {
        if(!haveBest) { best = target1h; haveBest = true; }
        else if(direction == "BUY") best = MathMin(best, target1h);
        else best = MathMax(best, target1h);
    }

    return haveBest ? best : 0.0;
}

double FindSwingOnTimeframe(ENUM_TIMEFRAMES tf, string direction)
{
    MqlRates rates[];
    int copied = CopyRates(_Symbol, tf, SwingExcludeRecentBars, SwingLookbackBars, rates);
    if(copied <= 0) return 0.0;

    double best = (direction == "BUY") ? rates[0].high : rates[0].low;
    for(int i = 1; i < copied; i++)
    {
        if(direction == "BUY") best = MathMax(best, rates[i].high);
        else best = MathMin(best, rates[i].low);
    }
    return best;
}

//+------------------------------------------------------------------+
//| Translates RiskMode/LotSize/RiskPercent into an actual lot size.  |
//| RISK_FIXED_LOT just returns LotSize; the percent-risk modes size  |
//| the position so that riskDistancePrice (entry-to-SL distance)     |
//| equals RiskPercent% of the account balance/equity, normalized to  |
//| the symbol's lot step/min/max.                                    |
//+------------------------------------------------------------------+
double CalculateLotSize(double riskDistancePrice)
{
    if(RiskMode == RISK_FIXED_LOT || riskDistancePrice <= 0)
        return LotSize;

    double accountValue = (RiskMode == RISK_PERCENT_EQUITY) ? AccountInfoDouble(ACCOUNT_EQUITY) : AccountInfoDouble(ACCOUNT_BALANCE);
    double riskAmount = accountValue * (RiskPercent / 100.0);

    double tickValue = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_VALUE);
    double tickSize = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE);
    if(tickValue <= 0 || tickSize <= 0)
        return LotSize; // fallback if symbol info unavailable

    double lossPerLot = (riskDistancePrice / tickSize) * tickValue;
    if(lossPerLot <= 0)
        return LotSize;

    double lots = riskAmount / lossPerLot;

    double lotStep = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP);
    double minLot = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
    double maxLot = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MAX);
    if(lotStep > 0)
        lots = MathFloor(lots / lotStep) * lotStep;
    lots = MathMax(minLot, MathMin(maxLot, lots));

    return NormalizeDouble(lots, 2);
}
