import discord
import os
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv
from datetime import datetime, timezone

class EventContractCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="stats", description="顯示當日模擬交易統計數據")
    async def stats(self, interaction: discord.Interaction):
        try:
            await interaction.response.defer()
        except discord.errors.NotFound:
            return # Interaction already expired

        if not self.bot.store:
            await interaction.followup.send("DataStore not initialized.", ephemeral=True)
            return
        
        try:
            import asyncio
            date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            
            # Since we could have multiple strategies, we show summary for active ones
            # For now, let's just get stats for lgbm_v2 and catboost_v1 if they exist
            strategies = ["lgbm_v2", "catboost_v1", "xgboost_v1"]
            
            embed = discord.Embed(title=f"📊 當日統計 ({date_str} UTC)", color=discord.Color.gold())
            
            for strategy_name in strategies:
                try:
                    daily_stats = await asyncio.to_thread(self.bot.store.get_daily_stats, strategy_name, date_str)
                    if daily_stats.get('daily_trades', 0) > 0:
                        field_val = (
                            f"交易數: {daily_stats.get('daily_trades', 0)}\n"
                            f"PnL: {daily_stats.get('daily_loss', 0.0):+.2f} USDT\n"
                            f"連敗: {daily_stats.get('consecutive_losses', 0)}"
                        )
                        embed.add_field(name=f"🔹 {strategy_name}", value=field_val, inline=True)
                except Exception:
                    continue

            embed.add_field(name="系統狀態", value="⏸️ 已暫停" if self.bot.paused else "✅ 運行中", inline=False)
            
            if not embed.fields:
                embed.description = "今日尚無交易紀錄。"
                
            await interaction.followup.send(embed=embed)
        except Exception as e:
            try:
                await interaction.followup.send(f"❌ 取得統計數據時出錯: {e}", ephemeral=True)
            except Exception:
                pass

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
