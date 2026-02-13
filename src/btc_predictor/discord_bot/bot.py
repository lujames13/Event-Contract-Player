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
        await interaction.response.defer()
        
        if not self.bot.store:
            await interaction.followup.send("DataStore not initialized.", ephemeral=True)
            return
        
        try:
            date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            # 確保使用正確的策略名稱
            daily_stats = self.bot.store.get_daily_stats("xgboost_v1", date_str)
            
            embed = discord.Embed(title=f"📊 當日統計 ({date_str} UTC)", color=discord.Color.gold())
            embed.add_field(name="今日交易", value=str(daily_stats.get('daily_trades', 0)), inline=True)
            embed.add_field(name="今日虧損", value=f"{daily_stats.get('daily_loss', 0.0):.2f} USDT", inline=True)
            embed.add_field(name="連敗次數", value=str(daily_stats.get('consecutive_losses', 0)), inline=True)
            embed.add_field(name="狀態", value="⏸️ 已暫停" if self.bot.paused else "✅ 運行中", inline=False)
            
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

    async def on_ready(self):
        print(f'Logged in as {self.user} (ID: {self.user.id})')
        self.target_channel = self.get_channel(self.channel_id)
        if self.target_channel:
            print(f"Connected to channel: {self.target_channel.name}")
        else:
            print(f"Could not find channel with ID {self.channel_id}")

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
