import discord
import os
from discord.ext import commands
from dotenv import load_dotenv
from datetime import datetime

class EventContractBot(commands.Bot):
    def __init__(self, channel_id: int):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix="/", intents=intents)
        self.channel_id = channel_id
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

    async def setup_hook(self):
        # Setup commands
        @self.command(name="stats")
        async def stats(ctx):
            if not self.store:
                await ctx.send("DataStore not initialized.")
                return
            
            date_str = datetime.utcnow().strftime("%Y-%m-%d")
            
            # Simple stats for the main strategy
            daily_stats = self.store.get_daily_stats("xgboost_v1", date_str)
            
            embed = discord.Embed(title=f"📊 當日統計 ({date_str} UTC)", color=discord.Color.gold())
            embed.add_field(name="今日交易", value=str(daily_stats['daily_trades']), inline=True)
            embed.add_field(name="今日虧損", value=f"{daily_stats['daily_loss']:.2f} USDT", inline=True)
            embed.add_field(name="連敗次數", value=str(daily_stats['consecutive_losses']), inline=True)
            embed.add_field(name="狀態", value="⏸️ 已暫停" if self.paused else "✅ 運行中", inline=False)
            
            await ctx.send(embed=embed)

        @self.command(name="pause")
        async def pause(ctx):
            self.paused = True
            await ctx.send("⏸️ 模擬交易已暫停。")

        @self.command(name="resume")
        async def resume(ctx):
            self.paused = False
            await ctx.send("✅ 模擬交易已恢復。")

async def run_bot():
    load_dotenv()
    token = os.getenv("DISCORD_TOKEN")
    channel_id = int(os.getenv("DISCORD_CHANNEL_ID", 0))
    
    bot = EventContractBot(channel_id)
    async with bot:
        await bot.start(token)
