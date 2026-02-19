import discord
import os
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv
from datetime import datetime, timezone
import asyncio
import logging
import time
import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

CONFIDENCE_THRESHOLDS = {10: 0.606, 30: 0.591, 60: 0.591, 1440: 0.591}
PAYOUT_RATIOS = {10: 1.80, 30: 1.85, 60: 1.85, 1440: 1.85}
BREAKEVEN_WINRATES = {10: 0.5556, 30: 0.5405, 60: 0.5405, 1440: 0.5405}

TIMEFRAME_CHOICES = [
    app_commands.Choice(name="10 分鐘", value=10),
    app_commands.Choice(name="30 分鐘", value=30),
    app_commands.Choice(name="1 小時", value=60),
    app_commands.Choice(name="1 天", value=1440),
]

class EventContractCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def model_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        """動態回傳已載入的策略名稱。"""
        pipeline = getattr(self.bot, 'pipeline', None)
        if not pipeline or not pipeline.strategies:
            return []
        
        names = [s.name for s in pipeline.strategies]
        # 過濾：如果使用者已輸入部分文字，只顯示匹配的
        if current:
            names = [n for n in names if current.lower() in n.lower()]
        
        return [app_commands.Choice(name=n, value=n) for n in names[:25]]

    @app_commands.command(name="stats", description="顯示交易統計")
    @app_commands.describe(
        model="選擇策略（留空顯示所有）",
        timeframe="選擇時間框架（留空顯示所有）"
    )
    @app_commands.choices(timeframe=TIMEFRAME_CHOICES)
    async def stats(self, interaction: discord.Interaction,
                    model: str = None, 
                    timeframe: app_commands.Choice[int] = None):
        tf_value = timeframe.value if timeframe else None
        try:
            await interaction.response.defer()
        except discord.errors.NotFound:
            return

        if not self.bot.store:
            await interaction.followup.send("DataStore not initialized.", ephemeral=True)
            return

        try:
            # 1. Get strategy names dynamically
            pipeline = getattr(self.bot, 'pipeline', None)
            strategy_names = []
            if pipeline and pipeline.strategies:
                strategy_names = [s.name for s in pipeline.strategies]
            else:
                # Fallback to DB
                with self.bot.store._get_connection() as conn:
                    rows = conn.execute("SELECT DISTINCT strategy_name FROM simulated_trades").fetchall()
                    strategy_names = [r[0] for r in rows]

            if not strategy_names:
                await interaction.followup.send("目前尚無交易紀錄或載入策略。", ephemeral=True)
                return

            if model:
                # Detailed mode for a specific model
                if model not in strategy_names:
                    await interaction.followup.send(f"❌ 找不到策略: {model}", ephemeral=True)
                    return
                
                detail = await asyncio.to_thread(self.bot.store.get_strategy_detail, model, tf_value)
                date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
                daily_stats = await asyncio.to_thread(self.bot.store.get_daily_stats, model, date_str)
                
                # Query today's PnL separately since get_daily_stats only gives loss
                with self.bot.store._get_connection() as conn:
                    daily_pnl = conn.execute(
                        "SELECT COALESCE(SUM(pnl), 0) FROM simulated_trades WHERE strategy_name = ? AND open_time LIKE ? AND result IS NOT NULL",
                        (model, f"{date_str}%")
                    ).fetchone()[0]
                
                title = f"📊 {model} 詳細統計"
                if tf_value:
                    title += f" ({tf_value}m)"
                
                embed = discord.Embed(title=title, color=discord.Color.blue())
                embed.description = (
                    f"累計交易:   {detail['settled'] + detail['pending']} 筆（已結算 {detail['settled']} 筆）\n"
                    f"方向準確率: **{detail['da']:.1%}**\n"
                    f"  Higher:   {detail['higher_da']:.1%} ({detail['higher_wins']}/{detail['higher_total']})\n"
                    f"  Lower:    {detail['lower_da']:.1%} ({detail['lower_wins']}/{detail['lower_total']})\n"
                    f"總 PnL:     **{detail['total_pnl']:+.2f}** USDT\n"
                    f"最大回撤:   **{detail['max_drawdown']:.2f}** USDT\n"
                    f"今日交易:   {daily_stats['daily_trades']} 筆 | PnL: {daily_pnl:+.2f}\n"
                    f"連敗:       {daily_stats['consecutive_losses']}"
                )
                await interaction.followup.send(embed=embed)
            
            else:
                # Summary mode (Table)
                embed = discord.Embed(title="📊 交易統計摘要", color=discord.Color.gold())
                header = "策略           | TF  | 交易 | DA     | PnL\n"
                sep = "─────────────────\n"
                rows_text = []
                
                total_trades = 0
                total_wins = 0
                total_settled = 0
                total_pnl = 0.0

                # Determine which (name, tf) pairs to show
                pairs_to_show = []
                with self.bot.store._get_connection() as conn:
                    query = "SELECT DISTINCT strategy_name, timeframe_minutes FROM simulated_trades"
                    if tf_value:
                        query += " WHERE timeframe_minutes = ?"
                        db_rows = conn.execute(query, (tf_value,)).fetchall()
                    else:
                        db_rows = conn.execute(query).fetchall()
                    pairs_to_show = db_rows

                # Sort by name, then tf
                pairs_to_show.sort(key=lambda x: (x[0], x[1]))

                for name, tf in pairs_to_show:
                    s = await asyncio.to_thread(self.bot.store.get_strategy_detail, name, tf)
                    if s['settled'] == 0 and s['pending'] == 0:
                        continue
                    
                    tf_str = f"{tf}m"
                    row = f"{name:<14} | {tf_str:>3} | {s['settled']+s['pending']:>4} | {s['da']:>5.1%} | {s['total_pnl']:+.2f}\n"
                    rows_text.append(row)
                    
                    total_trades += (s['settled'] + s['pending'])
                    total_wins += s['wins']
                    total_settled += s['settled']
                    total_pnl += s['total_pnl']

                if not rows_text:
                    embed.description = "尚無符合條件的交易紀錄。"
                else:
                    avg_da = total_wins / total_settled if total_settled > 0 else 0.0
                    footer = f"總計           |     | {total_trades:>4} | {avg_da:>5.1%} | {total_pnl:+.2f}"
                    embed.description = f"```\n{header}{sep}{''.join(rows_text)}{sep}{footer}\n```"
                
                await interaction.followup.send(embed=embed)

        except Exception as e:
            await interaction.followup.send(f"❌ 取得統計數據時出錯: {e}", ephemeral=True)

    @stats.autocomplete('model')
    async def stats_model_autocomplete(self, interaction: discord.Interaction, current: str):
        return await self.model_autocomplete(interaction, current)

    @app_commands.command(name="calibration", description="顯示模型校準分析摘要")
    @app_commands.describe(strategy="選擇策略（留空顯示所有）")
    async def calibration(self, interaction: discord.Interaction, strategy: str = None):
        try:
            await interaction.response.defer()
        except discord.errors.NotFound:
            return

        if not self.bot.store:
            await interaction.followup.send("DataStore not initialized.", ephemeral=True)
            return

        try:
            df = await asyncio.to_thread(self.bot.store.get_settled_signals, strategy_name=strategy)
            
            if df.empty:
                await interaction.followup.send("尚無足夠已結算資料進行分析。", ephemeral=True)
                return

            embed = discord.Embed(title="📊 校準分析摘要", color=discord.Color.purple())
            
            # Group by strategy and timeframe
            grouped = df.groupby(['strategy_name', 'timeframe_minutes'])
            
            summary_texts = []
            for (name, tf), group in grouped:
                total_count = len(group)
                acc = group['is_correct'].mean()
                
                # ECE calculation (simplified for embed - 3 bins)
                bins = [(0.50, 0.60), (0.60, 0.70), (0.70, 1.01)]
                ece = 0.0
                for start, end in bins:
                    mask = (group['confidence'] >= start) & (group['confidence'] < end)
                    bin_df = group[mask]
                    if not bin_df.empty:
                        ece += (len(bin_df) / total_count) * abs(bin_df['is_correct'].mean() - bin_df['confidence'].mean())
                
                # Optimal threshold search (Simplified)
                payout = PAYOUT_RATIOS.get(tf, 1.85)
                current_threshold = CONFIDENCE_THRESHOLDS.get(tf, 0.591)
                
                best_pnl_day = -999.0
                best_threshold = 0.50
                current_pnl_day = 0.0
                
                ts_min = pd.to_datetime(group['timestamp']).min()
                ts_max = pd.to_datetime(group['timestamp']).max()
                duration_days = max(0.1, (ts_max - ts_min).total_seconds() / 86400)
                
                threshold_range = np.arange(0.50, 0.71, 0.01)
                for t in threshold_range:
                    passed = group[group['confidence'] >= t]
                    if passed.empty: continue
                    
                    # Estimate avg bet
                    # Use a vectorized calculation for efficiency if possible
                    c = passed['confidence'].values
                    bets = 5 + (c - t) / (1.0 - t) * 15
                    bets = np.clip(bets, 5, 20)
                    avg_bet = np.mean(bets)
                    
                    pnl_trade = avg_bet * (passed['is_correct'].mean() * payout - 1)
                    pnl_day = pnl_trade * (len(passed) / duration_days)
                    
                    if pnl_day > best_pnl_day:
                        best_pnl_day = pnl_day
                        best_threshold = t
                    if abs(t - current_threshold) < 0.005:
                        current_pnl_day = pnl_day
                
                summary_text = (
                    f"**{name} | {tf}m** (已結算: {total_count} 筆)\n"
                    f"  正確率: {acc:.2%} | ECE: {ece:.3f}\n"
                    f"  當前閾值: {current_threshold:.3f} | 建議閾值: {best_threshold:.2f}\n"
                    f"  E[PnL/day] 當前: {current_pnl_day:+.2f} | 最佳: {best_pnl_day:+.2f}\n"
                )
                summary_texts.append(summary_text)
            
            embed.description = "\n".join(summary_texts)
            
            if len(df) < 200:
                embed.set_footer(text="⚠️ 樣本量 < 200，統計信心有限\n💡 完整報告: uv run python scripts/analyze_calibration.py")
            else:
                embed.set_footer(text="💡 完整報告: uv run python scripts/analyze_calibration.py")
                
            await interaction.followup.send(embed=embed)

        except Exception as e:
            logger.error(f"Error in calibration command: {e}", exc_info=True)
            await interaction.followup.send(f"❌ 執行分析時出錯: {e}", ephemeral=True)

    @calibration.autocomplete('strategy')
    async def calibration_strategy_autocomplete(self, interaction: discord.Interaction, current: str):
        return await self.model_autocomplete(interaction, current)

    @app_commands.command(name="pause", description="暫停模擬交易訊號推送")
    async def pause(self, interaction: discord.Interaction):
        self.bot.paused = True
        await interaction.response.send_message("⏸️ 模擬交易已暫停。")

    @app_commands.command(name="resume", description="恢復模擬交易訊號推送")
    async def resume(self, interaction: discord.Interaction):
        self.bot.paused = False
        await interaction.response.send_message("✅ 模擬交易已恢復。")

    @app_commands.command(name="health", description="顯示系統健康狀態")
    async def health(self, interaction: discord.Interaction):
        try:
            await interaction.response.defer()
        except discord.errors.NotFound:
            return

        pipeline = getattr(self.bot, 'pipeline', None)
        store = getattr(self.bot, 'store', None)
        start_time = getattr(self.bot, 'start_time', None)

        embed = discord.Embed(title="🏥 系統健康檢查", color=discord.Color.blue())
        
        # 1. WebSocket & Pipeline Status
        if pipeline and pipeline.is_running:
            # Calculate last kline delay
            now = datetime.now(timezone.utc)
            if pipeline.last_kline_time:
                latest_kline_dt = max(pipeline.last_kline_time.values())
                delay_sec = int((now - latest_kline_dt).total_seconds())
                ws_status = f"✅ 連線中 | 最後收到 K 線: {delay_sec} 秒前"
            else:
                ws_status = "✅ 連線中 | 尚未收到資料"
            
            pipeline_status = f"✅ 運行中 | 已觸發策略: {pipeline.trigger_count} 次"
            strategy_count = f"{len(pipeline.strategies)} 個已載入"
        else:
            ws_status = "❌ 未連線"
            pipeline_status = "❌ 未運行"
            strategy_count = "0 個已載入"

        embed.add_field(name="🔌 WebSocket", value=ws_status, inline=False)
        embed.add_field(name="📊 Pipeline", value=pipeline_status, inline=False)
        embed.add_field(name="🤖 策略數", value=strategy_count, inline=False)

        # 2. DB Status
        if store:
            try:
                counts = await asyncio.to_thread(store.get_table_counts)
                db_status = f"✅ | ohlcv: {counts['ohlcv']:,} 筆 | trades: {counts['simulated_trades']:,} 筆"
                
                # Signal Layer Stats
                signal_stats = await asyncio.to_thread(store.get_signal_stats)
                if signal_stats['accuracy'] is not None:
                    acc_str = f"{signal_stats['accuracy']:.2%}"
                else:
                    acc_str = "N/A"
                signal_status = f"總計: {signal_stats['total']} 筆 | 已結算: {signal_stats['settled']} 筆 | 正確率: {acc_str}"

            except Exception as e:
                db_status = f"⚠️ 讀取出錯: {e}"
                signal_status = "⚠️ 讀取出錯"
        else:
            db_status = "❌ Store 未初始化"
            signal_status = "❌ Store 未初始化"
        
        embed.add_field(name="💾 DB", value=db_status, inline=False)
        embed.add_field(name="📡 Signals", value=signal_status, inline=False)

        # 3. Uptime
        if start_time:
            uptime = datetime.now(timezone.utc) - start_time
            days = uptime.days
            hours, remainder = divmod(uptime.seconds, 3600)
            minutes, seconds = divmod(remainder, 60)
            uptime_str = f"{days}d {hours}h {minutes}m"
        else:
            uptime_str = "未知"
        
        embed.add_field(name="⏱️ Uptime", value=uptime_str, inline=False)
        
        await interaction.followup.send(embed=embed)

    @app_commands.command(name="models", description="列出所有已載入模型")
    async def models(self, interaction: discord.Interaction):
        try:
            await interaction.response.defer()
        except discord.errors.NotFound:
            return

        pipeline = getattr(self.bot, 'pipeline', None)
        store = getattr(self.bot, 'store', None)

        if not pipeline:
            await interaction.followup.send("無法取得模型清單（Pipeline 未連線）", ephemeral=True)
            return

        if not store:
            await interaction.followup.send("無法取得統計數據（Store 未初始化）", ephemeral=True)
            return

        embed = discord.Embed(title="🤖 已載入模型", color=discord.Color.blue())
        
        if not pipeline.strategies:
            embed.description = "目前未載入任何策略。"
            await interaction.followup.send(embed=embed)
            return

        for strategy in pipeline.strategies:
            summary = await asyncio.to_thread(store.get_strategy_summary, strategy.name)
            
            timeframes_str = ", ".join([f"{tf}m" for tf in strategy.available_timeframes])
            
            if summary['settled_trades'] > 0:
                stats_str = (
                    f"Live 交易: {summary['total_trades']} 筆 | "
                    f"DA: {summary['da']:.1%} | "
                    f"PnL: {summary['total_pnl']:+.2f} USDT"
                )
            else:
                stats_str = f"Live 交易: {summary['total_trades']} 筆 | 尚無結算紀錄"
                
            field_val = (
                f"Timeframes: {timeframes_str}\n"
                f"{stats_str}"
            )
            embed.add_field(name=f"📈 {strategy.name}", value=field_val, inline=False)

        await interaction.followup.send(embed=embed)

    @app_commands.command(name="predict", description="手動觸發即時預測")
    @app_commands.describe(timeframe="選擇預測時間框架")
    @app_commands.choices(timeframe=TIMEFRAME_CHOICES)
    async def predict(self, interaction: discord.Interaction,
                      timeframe: app_commands.Choice[int] = None):
        tf_value = timeframe.value if timeframe else None
        try:
            await interaction.response.defer()
        except discord.errors.NotFound:
            return

        pipeline = getattr(self.bot, 'pipeline', None)
        store = getattr(self.bot, 'store', None)

        if not pipeline:
            await interaction.followup.send("❌ Pipeline 未連線，無法預測。", ephemeral=True)
            return

        if not store:
            await interaction.followup.send("❌ Store 未初始化，無法從 DB 讀取數據。", ephemeral=True)
            return

        # 1. Get latest OHLCV
        try:
            df = await asyncio.to_thread(store.get_latest_ohlcv, "BTCUSDT", "1m", limit=500)
            if df is None or df.empty:
                await interaction.followup.send("❌ 資料庫無 K 線數據，無法預測。", ephemeral=True)
                return
        except Exception as e:
            await interaction.followup.send(f"❌ 讀取 OHLCV 出錯: {e}", ephemeral=True)
            return

        latest_kline_dt = df.index[-1].to_pydatetime()
        latest_kline_str = latest_kline_dt.strftime("%Y-%m-%d %H:%M UTC")
        
        start_time = time.time()
        results = []
        
        # 2. Iterate strategies and timeframes
        for strategy in pipeline.strategies:
            tfs = strategy.available_timeframes
            if tf_value:
                if tf_value not in tfs:
                    continue
                tfs = [tf_value]
            
            for tf in tfs:
                try:
                    signal = await asyncio.to_thread(strategy.predict, df, tf)
                    
                    threshold = CONFIDENCE_THRESHOLDS.get(tf, 0.6)
                    is_above = signal.confidence >= threshold
                    
                    if is_above:
                        # bet = 5 + (confidence - threshold) / (1.0 - threshold) * 15
                        bet_amount = 5 + (signal.confidence - threshold) / (1.0 - threshold) * 15
                        bet_str = f"✅ {bet_amount:.1f} USDT（超過閾值 {threshold}）"
                    else:
                        bet_str = f"❌ 不下注（低於閾值 {threshold}）"
                    
                    results.append({
                        "strategy": strategy.name,
                        "tf": tf,
                        "direction": signal.direction.upper(),
                        "confidence": signal.confidence,
                        "bet": bet_str,
                        "error": None
                    })
                except Exception as e:
                    results.append({
                        "strategy": strategy.name,
                        "tf": tf,
                        "error": str(e)
                    })

        if not results:
            await interaction.followup.send("⚠️ 沒有可預測的策略或 timeframe。", ephemeral=True)
            return

        # 3. Format Embed
        duration = time.time() - start_time
        embed = discord.Embed(
            title=f"🔮 即時預測（基於最新 K 線: {latest_kline_str}）",
            color=discord.Color.blue()
        )
        
        for res in results:
            if res['error']:
                field_name = f"📈 {res['strategy']} | {res['tf']}m"
                field_val = f"❌ 推理失敗: {res['error']}"
            else:
                field_name = f"📈 {res['strategy']} | {res['tf']}m"
                field_val = (
                    f"方向: **{res['direction']}** | 信心度: **{res['confidence']:.4f}**\n"
                    f"下注建議: {res['bet']}"
                )
            embed.add_field(name=field_name, value=field_val, inline=False)
            
        embed.set_footer(text=f"⏱️ 推理耗時: {duration:.2f}s")
        await interaction.followup.send(embed=embed)

    @app_commands.command(name="help", description="顯示所有可用指令")
    async def help_command(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="📖 Event Contract Bot — 指令總覽",
            color=discord.Color.blue()
        )
        
        embed.add_field(
            name="🔍 觀測",
            value=(
                "`/health` — 系統健康檢查（WebSocket、Pipeline、DB）\n"
                "`/models` — 已載入模型及 live 表現"
            ),
            inline=False
        )
        
        embed.add_field(
            name="📊 交易",
            value=(
                "`/predict [timeframe]` — 即時預測（可選時間框架）\n"
                "`/stats [model] [timeframe]` — 交易統計摘要或詳細"
            ),
            inline=False
        )
        
        embed.add_field(
            name="⚙️ 控制",
            value=(
                "`/pause` — 暫停訊號推送\n"
                "`/resume` — 恢復訊號推送"
            ),
            inline=False
        )
        
        embed.set_footer(text="💡 所有參數都可從下拉選單選取，不需手動輸入")
        
        await interaction.response.send_message(embed=embed)

class EventContractBot(commands.Bot):
    def __init__(self, channel_id: int, guild_id: int = None):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix="!", intents=intents)
        self.channel_id = channel_id
        self.guild_id = guild_id
        self.target_channel = None
        self.paused = False
        self.store = None # Will be set by caller
        self.pipeline = None
        self.start_time = None

    async def on_ready(self):
        logger.info(f'Logged in as {self.user} (ID: {self.user.id})')
        self.target_channel = self.get_channel(self.channel_id)
        if self.target_channel:
            logger.info(f"Connected to channel: {self.target_channel.name} ({self.channel_id})")
        else:
            logger.warning(f"Could not find channel with ID {self.channel_id}")
        
        logger.info(f"Bot is in {len(self.guilds)} guilds:")
        for guild in self.guilds:
            logger.info(f" - {guild.name} (ID: {guild.id})")

        if not self.start_time:
            self.start_time = datetime.now(timezone.utc)

    async def setup_hook(self):
        logger.info("Bot setup_hook started.")
        try:
            # Add the Cog
            await self.add_cog(EventContractCog(self))
            logger.info("EventContractCog added.")
            
            # Sync commands
            if self.guild_id:
                guild = discord.Object(id=self.guild_id)
                logger.info(f"Syncing slash commands to guild {self.guild_id}...")
                self.tree.copy_global_to(guild=guild)
                await self.tree.sync(guild=guild)
            else:
                logger.info("Syncing slash commands globally (might take some time)...")
                await self.tree.sync()
            logger.info("Slash commands synced successfully.")
        except Exception as e:
            logger.error(f"Error during bot setup_hook: {e}", exc_info=True)

    async def send_signal(self, trade):
        """
        Send a trade signal message.
        """
        if not self.target_channel or self.paused:
            return
            
        threshold = CONFIDENCE_THRESHOLDS.get(trade.timeframe_minutes, 0.6)
        is_above = trade.confidence >= threshold
        
        embed = discord.Embed(
            title=f"🔮 [{trade.strategy_name}] BTCUSDT {trade.timeframe_minutes}m → {trade.direction.upper()}",
            color=discord.Color.blue()
        )
        
        desc = (
            f"📊 信心度:    {trade.confidence:.4f}\n"
            f"💰 下注建議:  {'✅' if is_above else '❌'} {trade.bet_amount:.1f} USDT\n"
            f"📍 開倉價:    ${trade.open_price:,.2f}\n"
            f"⏰ 到期:      {trade.expiry_time} UTC\n"
            f"🎯 閾值:      {threshold}（{'已超過' if is_above else '未達'}）"
        )
        embed.description = desc
        
        await self.target_channel.send(embed=embed)

    async def send_settlement(self, trade):
        """
        Send a settlement notification.
        """
        if not self.target_channel:
            return
            
        is_win = getattr(trade, 'result', '') == 'win'
        result_emoji = "✅ WIN" if is_win else "❌ LOSE"
        color = discord.Color.green() if is_win else discord.Color.red()
        
        embed = discord.Embed(
            title=f"{result_emoji} [{trade.strategy_name}] {trade.timeframe_minutes}m {trade.direction.upper()}",
            color=color
        )
        
        desc = (
            f"開倉: ${trade.open_price:,.2f} → 收盤: ${trade.close_price:,.2f}\n"
            f"盈虧: **{trade.pnl:+.2f}** USDT\n"
        )
        
        # Add cumulative stats
        try:
            summary = await asyncio.to_thread(self.store.get_strategy_summary, trade.strategy_name)
            if summary and summary.get('settled_trades', 0) > 0:
                desc += "─────────────────\n"
                desc += f"📊 累計: {summary['total_trades']} 筆 | DA {summary['da']:.1%} | PnL {summary['total_pnl']:+.2f}"
        except Exception:
            # Skip if error (e.g. store not set or DB error)
            pass
            
        embed.description = desc
        await self.target_channel.send(embed=embed)

async def run_bot():
    load_dotenv()
    token = os.getenv("DISCORD_TOKEN")
    channel_id = int(os.getenv("DISCORD_CHANNEL_ID", 0))
    guild_id = os.getenv("DISCORD_GUILD_ID")
    if guild_id:
        guild_id = int(guild_id)
    
    bot = EventContractBot(channel_id, guild_id)
    async with bot:
        await bot.start(token)
