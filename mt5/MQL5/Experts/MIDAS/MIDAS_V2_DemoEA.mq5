#property copyright "MIDAS v2"
#property version   "2.00"
#property strict
#property description "MIDAS v2 demo-only execution EA. Real accounts are hard-blocked."

#include <Trade/Trade.mqh>

input bool   InpEnableDemoExecution      = false;
input string InpCommandFile              = "MIDAS\\midas_command.csv";
input string InpStatusFile               = "MIDAS\\midas_ea_status.csv";
input int    InpPollSeconds              = 1;
input int    InpDeviationPoints          = 30;
input bool   InpMoveToBreakevenAtTP1     = true;

CTrade trade;

string GVLastDecision()
{
   return "MIDAS_V2_LAST_DECISION";
}

string GVTP1(const long magic)
{
   return "MIDAS_V2_TP1_" + IntegerToString((int)magic);
}

string GVEntry(const long magic)
{
   return "MIDAS_V2_ENTRY_" + IntegerToString((int)magic);
}

string GVTp2(const long magic)
{
   return "MIDAS_V2_TP2_" + IntegerToString((int)magic);
}

void WriteStatus(const string state,const string detail,const long decision_id=0,const ulong ticket=0)
{
   int h=FileOpen(InpStatusFile,FILE_WRITE|FILE_CSV|FILE_ANSI|FILE_COMMON,';');
   if(h==INVALID_HANDLE)
      return;
   FileWrite(h,"schema","time","state","detail","decision_id","position_ticket","real_orders_allowed");
   FileWrite(h,"MIDAS_V2_EA_STATUS_1",(long)TimeCurrent(),state,detail,decision_id,(long)ticket,0);
   FileClose(h);
}

bool DemoAccountAllowed(string &reason)
{
   if(!InpEnableDemoExecution)
   {
      reason="EA_EXECUTION_DISABLED";
      return false;
   }

   ENUM_ACCOUNT_TRADE_MODE mode=(ENUM_ACCOUNT_TRADE_MODE)AccountInfoInteger(ACCOUNT_TRADE_MODE);
   if(mode!=ACCOUNT_TRADE_MODE_DEMO)
   {
      reason="REAL_OR_NONDEMO_ACCOUNT_BLOCKED";
      return false;
   }
   if(!TerminalInfoInteger(TERMINAL_TRADE_ALLOWED))
   {
      reason="TERMINAL_AUTOTRADING_DISABLED";
      return false;
   }
   if(!MQLInfoInteger(MQL_TRADE_ALLOWED))
   {
      reason="EA_TRADING_NOT_ALLOWED";
      return false;
   }
   if(!AccountInfoInteger(ACCOUNT_TRADE_ALLOWED) || !AccountInfoInteger(ACCOUNT_TRADE_EXPERT))
   {
      reason="ACCOUNT_EXPERT_TRADING_NOT_ALLOWED";
      return false;
   }
   reason="OK";
   return true;
}

bool FindMidasPosition(const string symbol,const long magic,ulong &ticket)
{
   ticket=0;
   for(int i=PositionsTotal()-1;i>=0;i--)
   {
      ulong t=PositionGetTicket(i);
      if(t==0 || !PositionSelectByTicket(t))
         continue;
      if(PositionGetString(POSITION_SYMBOL)!=symbol)
         continue;
      if((long)PositionGetInteger(POSITION_MAGIC)!=magic)
         continue;
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
      if(t==0 || !PositionSelectByTicket(t))
         continue;
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

bool ReadCommand(
   string &schema,long &decision_id,string &symbol,string &action,
   double &volume,double &entry,double &sl,double &tp1,double &tp2,
   double &max_spread_points,double &max_drift_points,long &expires_epoch,
   long &magic,long &real_orders_allowed)
{
   int h=FileOpen(InpCommandFile,FILE_READ|FILE_CSV|FILE_ANSI|FILE_COMMON|FILE_SHARE_READ,';');
   if(h==INVALID_HANDLE)
      return false;

   for(int i=0;i<14 && !FileIsEnding(h);i++)
      FileReadString(h);

   if(FileIsEnding(h))
   {
      FileClose(h);
      return false;
   }

   schema=FileReadString(h);
   decision_id=(long)StringToInteger(FileReadString(h));
   symbol=FileReadString(h);
   action=FileReadString(h);
   volume=StringToDouble(FileReadString(h));
   entry=StringToDouble(FileReadString(h));
   sl=StringToDouble(FileReadString(h));
   tp1=StringToDouble(FileReadString(h));
   tp2=StringToDouble(FileReadString(h));
   max_spread_points=StringToDouble(FileReadString(h));
   max_drift_points=StringToDouble(FileReadString(h));
   expires_epoch=(long)StringToInteger(FileReadString(h));
   magic=(long)StringToInteger(FileReadString(h));
   real_orders_allowed=(long)StringToInteger(FileReadString(h));
   FileClose(h);
   return true;
}

double NormalizeVolumeSafe(const string symbol,const double requested)
{
   double vmin=SymbolInfoDouble(symbol,SYMBOL_VOLUME_MIN);
   double vmax=SymbolInfoDouble(symbol,SYMBOL_VOLUME_MAX);
   double step=SymbolInfoDouble(symbol,SYMBOL_VOLUME_STEP);
   if(vmin<=0 || vmax<=0 || step<=0 || requested<vmin || requested>vmax)
      return 0.0;
   double steps=MathFloor((requested+1e-12)/step);
   double value=steps*step;
   if(value<vmin || value>vmax)
      return 0.0;
   return NormalizeDouble(value,8);
}

bool GeometryValid(const string action,const double price,const double sl,const double tp1,const double tp2)
{
   if(action=="BUY")
      return (sl<price && price<tp1 && tp1<tp2);
   if(action=="SELL")
      return (tp2<tp1 && tp1<price && price<sl);
   return false;
}

void ManagePosition()
{
   string reason;
   if(!DemoAccountAllowed(reason))
      return;

   for(int i=PositionsTotal()-1;i>=0;i--)
   {
      ulong ticket=PositionGetTicket(i);
      if(ticket==0 || !PositionSelectByTicket(ticket))
         continue;

      long magic=(long)PositionGetInteger(POSITION_MAGIC);
      if(!GlobalVariableCheck(GVTP1(magic)) || !GlobalVariableCheck(GVEntry(magic)))
         continue;

      string symbol=PositionGetString(POSITION_SYMBOL);
      long ptype=(long)PositionGetInteger(POSITION_TYPE);
      double current_sl=PositionGetDouble(POSITION_SL);
      double current_tp=PositionGetDouble(POSITION_TP);
      double tp1=GlobalVariableGet(GVTP1(magic));
      double entry=GlobalVariableGet(GVEntry(magic));
      double tp2=GlobalVariableCheck(GVTp2(magic)) ? GlobalVariableGet(GVTp2(magic)) : current_tp;

      MqlTick tick;
      if(!SymbolInfoTick(symbol,tick))
         continue;

      bool reached=(ptype==POSITION_TYPE_BUY ? tick.bid>=tp1 : tick.ask<=tp1);
      if(!reached || !InpMoveToBreakevenAtTP1)
         continue;

      bool already_be=(ptype==POSITION_TYPE_BUY ? current_sl>=entry : (current_sl>0 && current_sl<=entry));
      if(already_be)
         continue;

      trade.SetExpertMagicNumber((ulong)magic);
      trade.SetDeviationInPoints(InpDeviationPoints);
      bool modified=trade.PositionModify(ticket,entry,tp2);
      if(modified && TradeResultAccepted())
         WriteStatus("MANAGED","STOP_MOVED_TO_BREAKEVEN",0,ticket);
      else
         WriteStatus("ERROR","BREAKEVEN_MODIFY_FAILED_"+IntegerToString((int)trade.ResultRetcode()),0,ticket);
   }
}

void ProcessCommand()
{
   string schema,symbol,action;
   long decision_id=0,expires_epoch=0,magic=0,real_orders_allowed=1;
   double volume=0,entry=0,sl=0,tp1=0,tp2=0,max_spread=0,max_drift=0;

   if(!ReadCommand(schema,decision_id,symbol,action,volume,entry,sl,tp1,tp2,max_spread,max_drift,expires_epoch,magic,real_orders_allowed))
   {
      WriteStatus("WAIT","COMMAND_FILE_UNAVAILABLE");
      return;
   }

   if(schema!="MIDAS_V2_EA_1")
   {
      WriteStatus("BLOCKED","SCHEMA_MISMATCH",decision_id);
      return;
   }
   if(real_orders_allowed!=0)
   {
      WriteStatus("BLOCKED","REAL_ORDER_INVARIANT_FAILED",decision_id);
      return;
   }
   if(expires_epoch<(long)TimeCurrent())
   {
      WriteStatus("SKIPPED","COMMAND_EXPIRED",decision_id);
      return;
   }
   if(action=="ABSTAIN")
   {
      WriteStatus("WAIT","ABSTAIN",decision_id);
      return;
   }
   if(action!="BUY" && action!="SELL")
   {
      WriteStatus("BLOCKED","INVALID_ACTION",decision_id);
      return;
   }

   string reason;
   if(!DemoAccountAllowed(reason))
   {
      WriteStatus("BLOCKED",reason,decision_id);
      return;
   }

   if(GlobalVariableCheck(GVLastDecision()))
   {
      long last=(long)GlobalVariableGet(GVLastDecision());
      if(last==decision_id)
      {
         WriteStatus("SKIPPED","DUPLICATE_DECISION",decision_id);
         return;
      }
   }

   ulong existing=0;
   if(FindMidasPosition(symbol,magic,existing))
   {
      WriteStatus("SKIPPED","MIDAS_POSITION_ALREADY_OPEN",decision_id,existing);
      return;
   }

   ulong any_position=0;
   if(FindAnyPositionOnSymbol(symbol,any_position))
   {
      WriteStatus("BLOCKED","SYMBOL_POSITION_ALREADY_EXISTS",decision_id,any_position);
      return;
   }

   if(!SymbolSelect(symbol,true))
   {
      WriteStatus("BLOCKED","SYMBOL_SELECT_FAILED",decision_id);
      return;
   }

   MqlTick tick;
   if(!SymbolInfoTick(symbol,tick))
   {
      WriteStatus("BLOCKED","TICK_UNAVAILABLE",decision_id);
      return;
   }

   double point=SymbolInfoDouble(symbol,SYMBOL_POINT);
   if(point<=0)
   {
      WriteStatus("BLOCKED","INVALID_POINT",decision_id);
      return;
   }

   double spread=(tick.ask-tick.bid)/point;
   if(spread<0 || spread>max_spread)
   {
      WriteStatus("BLOCKED","SPREAD_LIMIT",decision_id);
      return;
   }

   double price=(action=="BUY" ? tick.ask : tick.bid);
   double drift=MathAbs(price-entry)/point;
   if(drift>max_drift)
   {
      WriteStatus("BLOCKED","ENTRY_DRIFT_LIMIT",decision_id);
      return;
   }

   double safe_volume=NormalizeVolumeSafe(symbol,volume);
   if(safe_volume<=0)
   {
      WriteStatus("BLOCKED","INVALID_VOLUME",decision_id);
      return;
   }
   if(!GeometryValid(action,price,sl,tp1,tp2))
   {
      WriteStatus("BLOCKED","INVALID_EXECUTION_GEOMETRY",decision_id);
      return;
   }

   trade.SetExpertMagicNumber((ulong)magic);
   trade.SetDeviationInPoints(InpDeviationPoints);
   trade.SetTypeFillingBySymbol(symbol);

   bool sent=false;
   if(action=="BUY")
      sent=trade.Buy(safe_volume,symbol,0.0,sl,tp2,"MIDAS_V2_EA");
   else
      sent=trade.Sell(safe_volume,symbol,0.0,sl,tp2,"MIDAS_V2_EA");

   if(!sent || !TradeResultAccepted())
   {
      WriteStatus("ERROR","ORDER_FAILED_"+IntegerToString((int)trade.ResultRetcode()),decision_id);
      return;
   }

   ulong ticket=0;
   FindMidasPosition(symbol,magic,ticket);
   GlobalVariableSet(GVLastDecision(),(double)decision_id);
   GlobalVariableSet(GVTP1(magic),tp1);
   GlobalVariableSet(GVEntry(magic),price);
   GlobalVariableSet(GVTp2(magic),tp2);
   WriteStatus("OPENED",action,decision_id,ticket);
}

int OnInit()
{
   if(InpPollSeconds<1)
      return INIT_PARAMETERS_INCORRECT;
   EventSetTimer(InpPollSeconds);
   WriteStatus("INIT","MIDAS_V2_EA_STARTED");
   return INIT_SUCCEEDED;
}

void OnDeinit(const int reason)
{
   EventKillTimer();
   WriteStatus("STOPPED","MIDAS_V2_EA_STOPPED");
}

void OnTimer()
{
   ManagePosition();
   ProcessCommand();
}

void OnTick()
{
   // Intentionally empty: decisions are polled on a timer, not generated from ticks.
}
