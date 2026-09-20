#property copyright "MIDAS v2"
#property version   "2.10"
#property strict
#property description "MIDAS v2 CRT+TBS cockpit and demo-only execution EA."

#include <Trade/Trade.mqh>

input bool   InpEnableDemoExecution      = false;
input string InpCommandFile              = "MIDAS\\midas_command.csv";
input string InpStatusFile               = "MIDAS\\midas_ea_status.csv";
input string InpEventFile                = "MIDAS\\midas_ea_events.csv";
input int    InpPollSeconds              = 1;
input int    InpDeviationPoints          = 30;
input bool   InpMoveToBreakevenAtTP1     = true;
input bool   InpUseEconomicCalendarLock   = true;
input int    InpNewsMinutesBefore         = 30;
input int    InpNewsMinutesAfter          = 15;
input bool   InpApplyCockpitStyle        = true;
input bool   InpShowCockpit              = true;
input bool   InpSaveSafeTemplateOnInit   = true;
input string InpTemplateName             = "MIDAS_V2_XAUUSD";

CTrade trade;
long g_midas_magic=56002026;

struct MidasCommand
{
   string schema;
   long   decision_id;
   string signal_id;
   string symbol;
   string action;
   string mode;
   string strategy;
   string setup_model;
   string h4_bias;
   string h1_bias;
   string setup;
   string ai_gate;
   string risk_gate;
   long   confidence;
   double risk_pct;
   double rr;
   double spread_points;
   double volume;
   double entry;
   double sl;
   double tp1;
   double tp2;
   double max_spread_points;
   double max_drift_points;
   long   expires_epoch;
   long   magic;
   long   real_orders_allowed;
};

string PFX="MIDAS2_";

string GVLastDecision(){ return "MIDAS_V2_LAST_DECISION"; }
string GVTP1(const long magic){ return "MIDAS_V2_TP1_"+IntegerToString((int)magic); }
string GVEntry(const long magic){ return "MIDAS_V2_ENTRY_"+IntegerToString((int)magic); }
string GVTp2(const long magic){ return "MIDAS_V2_TP2_"+IntegerToString((int)magic); }

void WriteStatus(const string state,const string detail,const long decision_id=0,const ulong ticket=0)
{
   int h=FileOpen(InpStatusFile,FILE_WRITE|FILE_CSV|FILE_ANSI|FILE_COMMON,';');
   if(h==INVALID_HANDLE) return;
   FileWrite(h,"schema","time","state","detail","decision_id","position_ticket","real_orders_allowed");
   FileWrite(h,"MIDAS_V2_EA_STATUS_2",(long)TimeCurrent(),state,detail,decision_id,(long)ticket,0);
   FileClose(h);
}

void AppendEvent(const string event_name,const long decision_id,const string signal_id,
                 const string symbol,const string action,const long position_id,const ulong deal_ticket,
                 const double volume,const double price,const double sl,const double tp1,const double tp2,
                 const double risk_cash,const double net_pnl)
{
   int h=FileOpen(InpEventFile,FILE_READ|FILE_WRITE|FILE_CSV|FILE_ANSI|FILE_COMMON|FILE_SHARE_READ|FILE_SHARE_WRITE,';');
   if(h==INVALID_HANDLE) return;
   if(FileSize(h)==0)
      FileWrite(h,"schema","time","event","decision_id","signal_id","symbol","action",
                "position_id","deal_ticket","volume","price","sl","tp1","tp2","risk_cash","net_pnl","real_orders_allowed");
   FileSeek(h,0,SEEK_END);
   FileWrite(h,"MIDAS_V2_EA_EVENT_1",(long)TimeCurrent(),event_name,decision_id,signal_id,symbol,action,
             position_id,(long)deal_ticket,volume,price,sl,tp1,tp2,risk_cash,net_pnl,0);
   FileFlush(h);
   FileClose(h);
}

bool DemoAccountAllowed(string &reason)
{
   if(!InpEnableDemoExecution){ reason="EA_EXECUTION_DISABLED"; return false; }

   ENUM_ACCOUNT_TRADE_MODE mode=(ENUM_ACCOUNT_TRADE_MODE)AccountInfoInteger(ACCOUNT_TRADE_MODE);
   if(mode!=ACCOUNT_TRADE_MODE_DEMO){ reason="REAL_OR_NONDEMO_ACCOUNT_BLOCKED"; return false; }
   if(!TerminalInfoInteger(TERMINAL_TRADE_ALLOWED)){ reason="TERMINAL_AUTOTRADING_DISABLED"; return false; }
   if(!MQLInfoInteger(MQL_TRADE_ALLOWED)){ reason="EA_TRADING_NOT_ALLOWED"; return false; }
   if(!AccountInfoInteger(ACCOUNT_TRADE_ALLOWED) || !AccountInfoInteger(ACCOUNT_TRADE_EXPERT))
   {
      reason="ACCOUNT_EXPERT_TRADING_NOT_ALLOWED";
      return false;
   }
   reason="OK";
   return true;
}


bool NewsExecutionAllowed(string &reason)
{
   if(!InpUseEconomicCalendarLock)
   {
      reason="NEWS_LOCK_DISABLED";
      return true;
   }
   datetime now=TimeTradeServer();
   if(now<=0)
   {
      reason="TRADE_SERVER_TIME_UNAVAILABLE";
      return false;
   }
   MqlCalendarValue values[];
   datetime from=now-(InpNewsMinutesAfter*60);
   datetime to=now+(InpNewsMinutesBefore*60);
   ResetLastError();
   int total=CalendarValueHistory(values,from,to,"","USD");
   if(total<0)
   {
      reason="ECONOMIC_CALENDAR_UNAVAILABLE_"+IntegerToString(GetLastError());
      return false;
   }
   for(int i=0;i<total;i++)
   {
      MqlCalendarEvent event;
      if(!CalendarEventById(values[i].event_id,event))
      {
         reason="ECONOMIC_CALENDAR_EVENT_LOOKUP_FAILED";
         return false;
      }
      if(event.importance==CALENDAR_IMPORTANCE_HIGH)
      {
         reason="HIGH_IMPACT_USD_EVENT_LOCK";
         return false;
      }
   }
   reason="NEWS_CLEAR";
   return true;
}

bool FindMidasPosition(const string symbol,const long magic,ulong &ticket)
{
   ticket=0;
   for(int i=PositionsTotal()-1;i>=0;i--)
   {
      ulong t=PositionGetTicket(i);
      if(t==0 || !PositionSelectByTicket(t)) continue;
      if(PositionGetString(POSITION_SYMBOL)!=symbol) continue;
      if((long)PositionGetInteger(POSITION_MAGIC)!=magic) continue;
      ticket=t;
      return true;
   }
   return false;
}

bool FindAnyPositionOnSymbol(const string symbol,ulong &ticket)
{
   ticket=0;
   for(int i=PositionsTotal()-1;i>=0;i--)
   {
      ulong t=PositionGetTicket(i);
      if(t==0 || !PositionSelectByTicket(t)) continue;
      if(PositionGetString(POSITION_SYMBOL)==symbol)
      {
         ticket=t;
         return true;
      }
   }
   return false;
}

bool TradeResultAccepted()
{
   uint retcode=trade.ResultRetcode();
   return (retcode==TRADE_RETCODE_DONE || retcode==TRADE_RETCODE_DONE_PARTIAL);
}

bool ReadCommand(MidasCommand &c)
{
   int h=FileOpen(InpCommandFile,FILE_READ|FILE_CSV|FILE_ANSI|FILE_COMMON|FILE_SHARE_READ,';');
   if(h==INVALID_HANDLE) return false;

   for(int i=0;i<27 && !FileIsEnding(h);i++) FileReadString(h);
   if(FileIsEnding(h)){ FileClose(h); return false; }

   c.schema=FileReadString(h);
   c.decision_id=(long)StringToInteger(FileReadString(h));
   c.signal_id=FileReadString(h);
   c.symbol=FileReadString(h);
   c.action=FileReadString(h);
   c.mode=FileReadString(h);
   c.strategy=FileReadString(h);
   c.setup_model=FileReadString(h);
   c.h4_bias=FileReadString(h);
   c.h1_bias=FileReadString(h);
   c.setup=FileReadString(h);
   c.ai_gate=FileReadString(h);
   c.risk_gate=FileReadString(h);
   c.confidence=(long)StringToInteger(FileReadString(h));
   c.risk_pct=StringToDouble(FileReadString(h));
   c.rr=StringToDouble(FileReadString(h));
   c.spread_points=StringToDouble(FileReadString(h));
   c.volume=StringToDouble(FileReadString(h));
   c.entry=StringToDouble(FileReadString(h));
   c.sl=StringToDouble(FileReadString(h));
   c.tp1=StringToDouble(FileReadString(h));
   c.tp2=StringToDouble(FileReadString(h));
   c.max_spread_points=StringToDouble(FileReadString(h));
   c.max_drift_points=StringToDouble(FileReadString(h));
   c.expires_epoch=(long)StringToInteger(FileReadString(h));
   c.magic=(long)StringToInteger(FileReadString(h));
   c.real_orders_allowed=(long)StringToInteger(FileReadString(h));
   FileClose(h);
   return true;
}

double NormalizeVolumeSafe(const string symbol,const double requested)
{
   double vmin=SymbolInfoDouble(symbol,SYMBOL_VOLUME_MIN);
   double vmax=SymbolInfoDouble(symbol,SYMBOL_VOLUME_MAX);
   double step=SymbolInfoDouble(symbol,SYMBOL_VOLUME_STEP);
   if(vmin<=0 || vmax<=0 || step<=0 || requested<vmin || requested>vmax) return 0.0;
   double steps=MathFloor((requested+1e-12)/step);
   double value=steps*step;
   if(value<vmin || value>vmax) return 0.0;
   return NormalizeDouble(value,8);
}

bool GeometryValid(const string action,const double price,const double sl,const double tp1,const double tp2)
{
   if(action=="BUY") return (sl<price && price<tp1 && tp1<tp2);
   if(action=="SELL") return (tp2<tp1 && tp1<price && price<sl);
   return false;
}

// ---------------- Cockpit UI ----------------

void ApplyCockpitStyle()
{
   if(!InpApplyCockpitStyle) return;
   ChartSetInteger(0,CHART_MODE,CHART_CANDLES);
   ChartSetInteger(0,CHART_SHOW_GRID,false);
   ChartSetInteger(0,CHART_SHOW_VOLUMES,CHART_VOLUME_HIDE);
   ChartSetInteger(0,CHART_COLOR_BACKGROUND,clrBlack);
   ChartSetInteger(0,CHART_COLOR_FOREGROUND,clrSilver);
   ChartSetInteger(0,CHART_COLOR_GRID,clrBlack);
   ChartSetInteger(0,CHART_COLOR_CANDLE_BULL,clrLimeGreen);
   ChartSetInteger(0,CHART_COLOR_CANDLE_BEAR,clrTomato);
   ChartSetInteger(0,CHART_COLOR_CHART_UP,clrLimeGreen);
   ChartSetInteger(0,CHART_COLOR_CHART_DOWN,clrTomato);
   ChartSetInteger(0,CHART_COLOR_BID,clrDodgerBlue);
   ChartSetInteger(0,CHART_COLOR_ASK,clrOrangeRed);
   ChartSetInteger(0,CHART_SHOW_BID_LINE,true);
   ChartSetInteger(0,CHART_SHOW_ASK_LINE,false);
   ChartSetInteger(0,CHART_SHIFT,true);
   ChartRedraw();
}

void SetPanelBackground()
{
   string name=PFX+"PANEL";
   if(ObjectFind(0,name)<0)
      ObjectCreate(0,name,OBJ_RECTANGLE_LABEL,0,0,0);
   ObjectSetInteger(0,name,OBJPROP_CORNER,CORNER_LEFT_UPPER);
   ObjectSetInteger(0,name,OBJPROP_XDISTANCE,12);
   ObjectSetInteger(0,name,OBJPROP_YDISTANCE,28);
   ObjectSetInteger(0,name,OBJPROP_XSIZE,285);
   ObjectSetInteger(0,name,OBJPROP_YSIZE,450);
   ObjectSetInteger(0,name,OBJPROP_BGCOLOR,clrBlack);
   ObjectSetInteger(0,name,OBJPROP_COLOR,clrDimGray);
   ObjectSetInteger(0,name,OBJPROP_BORDER_TYPE,BORDER_FLAT);
   ObjectSetInteger(0,name,OBJPROP_BACK,false);
   ObjectSetInteger(0,name,OBJPROP_SELECTABLE,false);
   ObjectSetInteger(0,name,OBJPROP_HIDDEN,true);
}

void SetLabel(const string key,const string text,const int y,const color clr,const int size=9)
{
   string name=PFX+"LBL_"+key;
   if(ObjectFind(0,name)<0)
      ObjectCreate(0,name,OBJ_LABEL,0,0,0);
   ObjectSetInteger(0,name,OBJPROP_CORNER,CORNER_LEFT_UPPER);
   ObjectSetInteger(0,name,OBJPROP_XDISTANCE,24);
   ObjectSetInteger(0,name,OBJPROP_YDISTANCE,y);
   ObjectSetInteger(0,name,OBJPROP_COLOR,clr);
   ObjectSetInteger(0,name,OBJPROP_FONTSIZE,size);
   ObjectSetString(0,name,OBJPROP_FONT,"Consolas");
   ObjectSetString(0,name,OBJPROP_TEXT,text);
   ObjectSetInteger(0,name,OBJPROP_SELECTABLE,false);
   ObjectSetInteger(0,name,OBJPROP_HIDDEN,true);
}

void SetTradeLevel(const string key,const double price,const color clr,const string label)
{
   string name=PFX+"LEVEL_"+key;
   if(price<=0)
   {
      ObjectDelete(0,name);
      return;
   }
   if(ObjectFind(0,name)<0)
      ObjectCreate(0,name,OBJ_HLINE,0,0,price);
   ObjectSetDouble(0,name,OBJPROP_PRICE,price);
   ObjectSetInteger(0,name,OBJPROP_COLOR,clr);
   ObjectSetInteger(0,name,OBJPROP_STYLE,STYLE_DASH);
   ObjectSetInteger(0,name,OBJPROP_WIDTH,1);
   ObjectSetString(0,name,OBJPROP_TEXT,label);
   ObjectSetInteger(0,name,OBJPROP_SELECTABLE,false);
   ObjectSetInteger(0,name,OBJPROP_HIDDEN,true);
}

void ClearTradeLevels()
{
   ObjectDelete(0,PFX+"LEVEL_ENTRY");
   ObjectDelete(0,PFX+"LEVEL_SL");
   ObjectDelete(0,PFX+"LEVEL_TP1");
   ObjectDelete(0,PFX+"LEVEL_TP2");
}

string AccountStateText()
{
   ENUM_ACCOUNT_TRADE_MODE mode=(ENUM_ACCOUNT_TRADE_MODE)AccountInfoInteger(ACCOUNT_TRADE_MODE);
   if(mode==ACCOUNT_TRADE_MODE_DEMO) return "DEMO ONLY";
   return "REAL BLOCKED";
}

color GateColor(const string value)
{
   if(value=="ALLOW" || value=="PASS" || value=="BUY" || value=="SELL") return clrLimeGreen;
   if(value=="REDUCE_RISK" || value=="ARMED") return clrOrange;
   return clrTomato;
}

void UpdateCockpit(const bool read_ok,const MidasCommand &c)
{
   if(!InpShowCockpit) return;
   SetPanelBackground();

   SetLabel("TITLE","MIDAS 2.0 | "+_Symbol,42,clrDodgerBlue,11);
   SetLabel("LINE1","------------------------------",60,clrDimGray,8);

   string mode=read_ok ? c.mode : "WAIT";
   string h4=read_ok ? c.h4_bias : "NEUTRAL";
   string h1=read_ok ? c.h1_bias : "NEUTRAL";
   string setup=read_ok ? c.setup : "WAIT";
   string ai=read_ok ? c.ai_gate : "BLOCK";
   string rg=read_ok ? c.risk_gate : "BLOCK";

   SetLabel("MODE","MODE        "+mode,78,clrWhite);
   SetLabel("H4","H4 BIAS     "+h4,96,clrWhite);
   SetLabel("H1","H1 BIAS     "+h1,114,clrWhite);
   SetLabel("MODEL","MODEL       "+(read_ok ? c.setup_model : "WAIT"),132,clrSilver);

   SetLabel("LINE2","------------------------------",150,clrDimGray,8);
   SetLabel("SETUP","SETUP       "+setup,168,GateColor(setup));
   SetLabel("AI","GPT GATE    "+ai,186,GateColor(ai));
   SetLabel("RISK_GATE","RISK GATE   "+rg,204,GateColor(rg));

   SetLabel("LINE3","------------------------------",222,clrDimGray,8);
   SetLabel("RISK","RISK        "+DoubleToString(read_ok ? c.risk_pct : 0.0,2)+"%",240,clrWhite);
   SetLabel("RR","RR          1:"+DoubleToString(read_ok ? c.rr : 0.0,2),258,clrWhite);
   SetLabel("SPREAD","SPREAD      "+DoubleToString(read_ok ? c.spread_points : 0.0,1)+" pts",276,clrWhite);
   SetLabel("LOT","LOT         "+DoubleToString(read_ok ? c.volume : 0.0,2),294,clrWhite);

   SetLabel("LINE4","------------------------------",312,clrDimGray,8);
   SetLabel("ENTRY","ENTRY       "+DoubleToString(read_ok ? c.entry : 0.0,_Digits),330,clrDodgerBlue);
   SetLabel("SL","SL          "+DoubleToString(read_ok ? c.sl : 0.0,_Digits),348,clrTomato);
   SetLabel("TP1","TP1         "+DoubleToString(read_ok ? c.tp1 : 0.0,_Digits),366,clrLimeGreen);
   SetLabel("TP2","TP2         "+DoubleToString(read_ok ? c.tp2 : 0.0,_Digits),384,clrLimeGreen);

   ulong ticket=0;
   bool has_pos=read_ok && FindMidasPosition(c.symbol,c.magic,ticket);
   SetLabel("POSITION","POSITION    "+(has_pos ? "OPEN" : "WAITING"),402,has_pos ? clrLimeGreen : clrOrange);
   SetLabel("ACCOUNT","ACCOUNT     "+AccountStateText(),420,
            AccountInfoInteger(ACCOUNT_TRADE_MODE)==ACCOUNT_TRADE_MODE_DEMO ? clrDodgerBlue : clrTomato);

   bool fresh=read_ok && c.expires_epoch>=(long)TimeCurrent();
   string heartbeat=fresh ? "MT5 o  MIDAS o  GPT o  RISK o  EA o" : "MT5 o  MIDAS x  GPT x  RISK x  EA o";
   SetLabel("HEART",heartbeat,448,fresh ? clrLimeGreen : clrOrange,8);

   if(read_ok && c.action!="ABSTAIN" && c.entry>0)
   {
      SetTradeLevel("ENTRY",c.entry,clrDodgerBlue,"MIDAS Entry");
      SetTradeLevel("SL",c.sl,clrTomato,"MIDAS SL");
      SetTradeLevel("TP1",c.tp1,clrLimeGreen,"MIDAS TP1");
      SetTradeLevel("TP2",c.tp2,clrGreen,"MIDAS TP2");
   }
   else ClearTradeLevels();

   ChartRedraw();
}

void DeleteCockpit()
{
   int total=ObjectsTotal(0,0,-1);
   for(int i=total-1;i>=0;i--)
   {
      string name=ObjectName(0,i,0,-1);
      if(StringFind(name,PFX)==0) ObjectDelete(0,name);
   }
   ChartRedraw();
}

// ---------------- Position management ----------------

void ManagePosition()
{
   string reason;
   if(!DemoAccountAllowed(reason)) return;

   for(int i=PositionsTotal()-1;i>=0;i--)
   {
      ulong ticket=PositionGetTicket(i);
      if(ticket==0 || !PositionSelectByTicket(ticket)) continue;

      long magic=(long)PositionGetInteger(POSITION_MAGIC);
      if(!GlobalVariableCheck(GVTP1(magic)) || !GlobalVariableCheck(GVEntry(magic))) continue;

      string symbol=PositionGetString(POSITION_SYMBOL);
      long ptype=(long)PositionGetInteger(POSITION_TYPE);
      double current_sl=PositionGetDouble(POSITION_SL);
      double current_tp=PositionGetDouble(POSITION_TP);
      double tp1=GlobalVariableGet(GVTP1(magic));
      double entry=GlobalVariableGet(GVEntry(magic));
      double tp2=GlobalVariableCheck(GVTp2(magic)) ? GlobalVariableGet(GVTp2(magic)) : current_tp;

      MqlTick tick;
      if(!SymbolInfoTick(symbol,tick)) continue;

      bool reached=(ptype==POSITION_TYPE_BUY ? tick.bid>=tp1 : tick.ask<=tp1);
      if(!reached || !InpMoveToBreakevenAtTP1) continue;

      bool already_be=(ptype==POSITION_TYPE_BUY ? current_sl>=entry : (current_sl>0 && current_sl<=entry));
      if(already_be) continue;

      trade.SetExpertMagicNumber((ulong)magic);
      trade.SetDeviationInPoints(InpDeviationPoints);
      bool modified=trade.PositionModify(ticket,entry,tp2);
      if(modified && TradeResultAccepted())
         WriteStatus("MANAGED","STOP_MOVED_TO_BREAKEVEN",0,ticket);
      else
         WriteStatus("ERROR","BREAKEVEN_MODIFY_FAILED_"+IntegerToString((int)trade.ResultRetcode()),0,ticket);
   }
}

void ProcessCommand(const MidasCommand &c)
{
   if(c.schema!="MIDAS_V2_EA_2"){ WriteStatus("BLOCKED","SCHEMA_MISMATCH",c.decision_id); return; }
   if(c.real_orders_allowed!=0){ WriteStatus("BLOCKED","REAL_ORDER_INVARIANT_FAILED",c.decision_id); return; }
   if(c.expires_epoch<(long)TimeCurrent()){ WriteStatus("SKIPPED","COMMAND_EXPIRED",c.decision_id); return; }
   if(c.action=="ABSTAIN"){ WriteStatus("WAIT","ABSTAIN",c.decision_id); return; }
   if(c.action!="BUY" && c.action!="SELL"){ WriteStatus("BLOCKED","INVALID_ACTION",c.decision_id); return; }

   string news_reason;
   if(!NewsExecutionAllowed(news_reason)){ WriteStatus("BLOCKED",news_reason,c.decision_id); return; }

   string reason;
   if(!DemoAccountAllowed(reason)){ WriteStatus("BLOCKED",reason,c.decision_id); return; }

   if(GlobalVariableCheck(GVLastDecision()))
   {
      long last=(long)GlobalVariableGet(GVLastDecision());
      if(last==c.decision_id){ WriteStatus("SKIPPED","DUPLICATE_DECISION",c.decision_id); return; }
   }

   ulong existing=0;
   if(FindMidasPosition(c.symbol,c.magic,existing))
   {
      WriteStatus("SKIPPED","MIDAS_POSITION_ALREADY_OPEN",c.decision_id,existing);
      return;
   }

   ulong any_position=0;
   if(FindAnyPositionOnSymbol(c.symbol,any_position))
   {
      WriteStatus("BLOCKED","SYMBOL_POSITION_ALREADY_EXISTS",c.decision_id,any_position);
      return;
   }

   if(!SymbolSelect(c.symbol,true)){ WriteStatus("BLOCKED","SYMBOL_SELECT_FAILED",c.decision_id); return; }

   MqlTick tick;
   if(!SymbolInfoTick(c.symbol,tick)){ WriteStatus("BLOCKED","TICK_UNAVAILABLE",c.decision_id); return; }

   double point=SymbolInfoDouble(c.symbol,SYMBOL_POINT);
   if(point<=0){ WriteStatus("BLOCKED","INVALID_POINT",c.decision_id); return; }

   double spread=(tick.ask-tick.bid)/point;
   if(spread<0 || spread>c.max_spread_points){ WriteStatus("BLOCKED","SPREAD_LIMIT",c.decision_id); return; }

   double price=(c.action=="BUY" ? tick.ask : tick.bid);
   double drift=MathAbs(price-c.entry)/point;
   if(drift>c.max_drift_points){ WriteStatus("BLOCKED","ENTRY_DRIFT_LIMIT",c.decision_id); return; }

   double safe_volume=NormalizeVolumeSafe(c.symbol,c.volume);
   if(safe_volume<=0){ WriteStatus("BLOCKED","INVALID_VOLUME",c.decision_id); return; }
   if(!GeometryValid(c.action,price,c.sl,c.tp1,c.tp2))
   {
      WriteStatus("BLOCKED","INVALID_EXECUTION_GEOMETRY",c.decision_id);
      return;
   }

   trade.SetExpertMagicNumber((ulong)c.magic);
   trade.SetDeviationInPoints(InpDeviationPoints);
   trade.SetTypeFillingBySymbol(c.symbol);

   bool sent=false;
   if(c.action=="BUY")
      sent=trade.Buy(safe_volume,c.symbol,0.0,c.sl,c.tp2,"MIDAS_V2_CRT_TBS");
   else
      sent=trade.Sell(safe_volume,c.symbol,0.0,c.sl,c.tp2,"MIDAS_V2_CRT_TBS");

   if(!sent || !TradeResultAccepted())
   {
      WriteStatus("ERROR","ORDER_FAILED_"+IntegerToString((int)trade.ResultRetcode()),c.decision_id);
      return;
   }

   ulong ticket=0;
   FindMidasPosition(c.symbol,c.magic,ticket);
   long position_id=0;
   if(ticket>0 && PositionSelectByTicket(ticket))
      position_id=(long)PositionGetInteger(POSITION_IDENTIFIER);
   double risk_cash=0.0;
   ENUM_ORDER_TYPE calc_type=(c.action=="BUY" ? ORDER_TYPE_BUY : ORDER_TYPE_SELL);
   double calc_profit=0.0;
   if(OrderCalcProfit(calc_type,c.symbol,safe_volume,price,c.sl,calc_profit))
      risk_cash=MathAbs(calc_profit);
   AppendEvent("OPENED",c.decision_id,c.signal_id,c.symbol,c.action,position_id,trade.ResultDeal(),
               safe_volume,price,c.sl,c.tp1,c.tp2,risk_cash,0.0);
   g_midas_magic=c.magic;
   GlobalVariableSet(GVLastDecision(),(double)c.decision_id);
   GlobalVariableSet(GVTP1(c.magic),c.tp1);
   GlobalVariableSet(GVEntry(c.magic),price);
   GlobalVariableSet(GVTp2(c.magic),c.tp2);
   WriteStatus("OPENED",c.action,c.decision_id,ticket);
}

int OnInit()
{
   if(InpPollSeconds<1) return INIT_PARAMETERS_INCORRECT;
   ApplyCockpitStyle();

   MidasCommand c;
   bool ok=ReadCommand(c);
   if(ok) g_midas_magic=c.magic;
   UpdateCockpit(ok,c);

   // Save a real terminal-native .tpl only while execution is safely disabled.
   if(InpSaveSafeTemplateOnInit && !InpEnableDemoExecution)
   {
      if(!ChartSaveTemplate(0,InpTemplateName))
         Print("MIDAS template save failed: ",GetLastError());
   }

   EventSetTimer(InpPollSeconds);
   WriteStatus("INIT","MIDAS_V2_EA_STARTED");
   return INIT_SUCCEEDED;
}

void OnDeinit(const int reason)
{
   EventKillTimer();
   WriteStatus("STOPPED","MIDAS_V2_EA_STOPPED");
   DeleteCockpit();
}

void OnTimer()
{
   ManagePosition();
   MidasCommand c;
   bool ok=ReadCommand(c);
   if(ok) g_midas_magic=c.magic;
   UpdateCockpit(ok,c);
   if(ok) ProcessCommand(c);
   else WriteStatus("WAIT","COMMAND_FILE_UNAVAILABLE");
}

void OnTick()
{
   // Strategy decisions are never generated from ticks inside the EA.
}


void OnTradeTransaction(const MqlTradeTransaction &trans,
                        const MqlTradeRequest &request,
                        const MqlTradeResult &result)
{
   if(trans.type!=TRADE_TRANSACTION_DEAL_ADD || trans.deal==0)
      return;
   if(!HistoryDealSelect(trans.deal))
      return;

   long magic=(long)HistoryDealGetInteger(trans.deal,DEAL_MAGIC);
   if(magic!=g_midas_magic)
      return;

   ENUM_DEAL_ENTRY entry_type=(ENUM_DEAL_ENTRY)HistoryDealGetInteger(trans.deal,DEAL_ENTRY);
   if(entry_type!=DEAL_ENTRY_OUT && entry_type!=DEAL_ENTRY_OUT_BY)
      return;

   long position_id=(long)HistoryDealGetInteger(trans.deal,DEAL_POSITION_ID);
   string symbol=HistoryDealGetString(trans.deal,DEAL_SYMBOL);
   double volume=HistoryDealGetDouble(trans.deal,DEAL_VOLUME);
   double price=HistoryDealGetDouble(trans.deal,DEAL_PRICE);
   double net_pnl=HistoryDealGetDouble(trans.deal,DEAL_PROFIT)
                 +HistoryDealGetDouble(trans.deal,DEAL_COMMISSION)
                 +HistoryDealGetDouble(trans.deal,DEAL_SWAP)
                 +HistoryDealGetDouble(trans.deal,DEAL_FEE);
   AppendEvent("CLOSE_DEAL",0,"",symbol,"",position_id,trans.deal,volume,price,0,0,0,0,net_pnl);
}
