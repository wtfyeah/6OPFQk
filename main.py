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

async def fetch_donutsmp_stats(username):
    """Fetch player stats from DonutSMP API using the stats endpoint"""
    headers = {"Authorization": f"Bearer {API_KEY}"}
    # Correct URL format from the working example
    stats_url = f"https://api.donutsmp.net/v1/stats/{username}"
    
    async with aiohttp.ClientSession() as session:
        try:
            logger.info(f"Fetching stats for {username}")
            async with session.get(stats_url, headers=headers) as response:
                logger.info(f"Response status for {username}: {response.status}")
                
                if response.status == 200:
                    data = await response.json()
                    stats = data.get("result", {})
                    
                    if stats:
                        # Get playtime (in seconds) and format it
                        playtime_seconds = stats.get("playtime", "0")
                        if playtime_seconds and playtime_seconds != "0":
                            hours = int(playtime_seconds) // 3600
                            minutes = (int(playtime_seconds) % 3600) // 60
                            playtime = f"{hours}h {minutes}m"
                        else:
                            playtime = "0h 0m"
                        
                        # Get balance and format it
                        balance_str = stats.get("money", "0")
                        if balance_str and balance_str != "0":
                            balance = f"${int(balance_str):,}"
                        else:
                            balance = "$0"
                        
                        logger.info(f"Successfully fetched stats for {username}")
                        return playtime, balance, True
                    else:
                        logger.warning(f"No stats data found for {username}")
                        return None, None, False
                
                elif response.status == 401:
                    logger.error("API key is invalid or unauthorized")
                    return None, None, False
                
                elif response.status == 500:
                    logger.info(f"Player {username} does not exist (received 500 status)")
                    return None, None, False
                
                else:
                    logger.warning(f"Unexpected response status {response.status} for {username}")
                    return None, None, False
                    
        except Exception as e:
            logger.error(f"Error fetching DonutSMP stats for {username}: {e}")
            return None, None, False

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
        logger.error(f'Could not find output channel with ID {OUTPUT_CHANNEL_ID}')
    
    await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.playing, name=".jarrr"))

@bot.event
async def on_message(message):
    if message.author.id == bot.user.id:
        return
    
    if message.channel.id == INPUT_CHANNEL_ID and message.webhook_id:
        logger.info(f"Webhook received in input channel #{message.channel.name}")
        
        username, session = parse_account_data(message.content)
        
        if not username or not session:
            logger.warning("Could not parse username or session from webhook")
            return
        
        logger.info(f"Parsed username: {username}")
        
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
