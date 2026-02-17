import discord
import os
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv
from datetime import datetime, timezone
import asyncio
import time

CONFIDENCE_THRESHOLDS = {10: 0.606, 30: 0.591, 60: 0.591, 1440: 0.591}

class EventContractCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="stats", description="顯示交易統計")
    @app_commands.describe(
        model="策略名稱（留空顯示所有）",
        timeframe="Timeframe 分鐘數（10/30/60/1440）"
    )
    async def stats(self, interaction: discord.Interaction,
                    model: str = None, timeframe: int = None):
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
                
                detail = await asyncio.to_thread(self.bot.store.get_strategy_detail, model, timeframe)
                date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
                daily_stats = await asyncio.to_thread(self.bot.store.get_daily_stats, model, date_str)
                
                # Query today's PnL separately since get_daily_stats only gives loss
                with self.bot.store._get_connection() as conn:
                    daily_pnl = conn.execute(
                        "SELECT COALESCE(SUM(pnl), 0) FROM simulated_trades WHERE strategy_name = ? AND open_time LIKE ? AND result IS NOT NULL",
                        (model, f"{date_str}%")
                    ).fetchone()[0]
                
                title = f"📊 {model} 詳細統計"
                if timeframe:
                    title += f" ({timeframe}m)"
                
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
                    if timeframe:
                        query += " WHERE timeframe_minutes = ?"
                        db_rows = conn.execute(query, (timeframe,)).fetchall()
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
                import asyncio
                counts = await asyncio.to_thread(store.get_table_counts)
                db_status = f"✅ | ohlcv: {counts['ohlcv']:,} 筆 | trades: {counts['simulated_trades']:,} 筆"
            except Exception as e:
                db_status = f"⚠️ 讀取出錯: {e}"
        else:
            db_status = "❌ Store 未初始化"
        
        embed.add_field(name="💾 DB", value=db_status, inline=False)

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

        import asyncio
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
    @app_commands.describe(timeframe="Timeframe 分鐘數（10/30/60/1440）")
    async def predict(self, interaction: discord.Interaction,
                      timeframe: int = None):
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
            if timeframe:
                if timeframe not in tfs:
                    continue
                tfs = [timeframe]
            
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
        print(f'Logged in as {self.user} (ID: {self.user.id})')
        self.target_channel = self.get_channel(self.channel_id)
        if self.target_channel:
            print(f"Connected to channel: {self.target_channel.name}")
        else:
            print(f"Could not find channel with ID {self.channel_id}")
        
        if not self.start_time:
            self.start_time = datetime.now(timezone.utc)

    async def setup_hook(self):
        # Add the Cog
        await self.add_cog(EventContractCog(self))
        
        # Sync commands
        if self.guild_id:
            guild = discord.Object(id=self.guild_id)
            # Remove global commands if we are using guild-specific sync to avoid duplicates
            # (Note: This only affects the bot's view, Discord may still cached global ones for a bit)
            # self.tree.clear_commands(guild=None) # Optional: uncomment if global commands persist too long
            print(f"Syncing slash commands to guild {self.guild_id}...")
            await self.tree.sync(guild=guild)
        else:
            print("Syncing slash commands globally (might take some time)...")
            await self.tree.sync()
        print("Slash commands synced.")

    async def send_signal(self, trade):
        """
        Send a trade signal message.
        """
        if not self.target_channel or self.paused:
            return
            
        embed = discord.Embed(
            title=f"🔮 [{trade.strategy_name}] BTCUSDT {trade.timeframe_minutes}m → {trade.direction.upper()}",
            color=discord.Color.blue()
        )
        embed.add_field(name="📊 信心度", value=f"{trade.confidence:.1%}", inline=True)
        embed.add_field(name="下注", value=f"${trade.bet_amount}", inline=True)
        embed.add_field(name="💰 開倉價", value=f"${trade.open_price:,.2f}", inline=False)
        embed.add_field(name="⏰ 到期", value=f"{trade.expiry_time} UTC", inline=False)
        
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
        embed.add_field(name="開倉", value=f"${trade.open_price:,.2f}", inline=True)
        embed.add_field(name="收盤", value=f"${trade.close_price:,.2f}", inline=True)
        embed.add_field(name="盈虧", value=f"**{trade.pnl:+.2f}** USDT", inline=False)
        
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
