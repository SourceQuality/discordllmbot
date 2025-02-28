# bot.py
import discord
from discord.ext import commands
import openai
import os
from datetime import datetime, timedelta
import asyncio
import logging
import json
import re

# Configure logging with configurable level
log_level = os.getenv('LOG_LEVEL', 'INFO').upper()
logging.basicConfig(
    level=getattr(logging, log_level, logging.INFO),
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# Configuration
intents = discord.Intents.default()
intents.messages = True
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

# API Configuration
API_KEY = os.getenv('API_KEY')
API_URL = os.getenv('API_URL', 'https://api.openai.com/v1')
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
SYSTEM_PROMPT_BASE = os.getenv('SYSTEM_PROMPT', '''You are a helpful Discord bot. Use the conversation context to respond appropriately. 
If asked to perform a function, respond with a JSON object enclosed in ```json``` markers. Supported functions:
- {"function": "remind", "time_hours": <hours as float>, "message": "<reminder text>"}
Example: ```json{"function": "remind", "time_hours": 2, "message": "feed the cat"}```''')
MODEL = os.getenv('MODEL', 'gpt-3.5-turbo')

# Configure OpenAI client with custom base URL
openai.api_key = API_KEY
openai.api_base = API_URL

# Constants
EMBED_THRESHOLD = 500

# Store scheduled tasks
scheduled_tasks = {}

# Function definitions
async def remind_me(channel, user, hours, message):
    try:
        await asyncio.sleep(hours * 3600)
        reminder_text = f"{user.mention}, here's your reminder: {message}"
        await channel.send(reminder_text)
        logger.info(f"Sent reminder to {user} in channel {channel}: {message}")
    except Exception as e:
        logger.error(f"Error in reminder task: {str(e)}", exc_info=True)

async def process_function_call(channel, user, response_text):
    json_pattern = r'```json\s*(.*?)\s*```'
    match = re.search(json_pattern, response_text, re.DOTALL)
    
    if match:
        try:
            func_data = json.loads(match.group(1))
            function_name = func_data.get("function")
            
            if function_name == "remind":
                hours = float(func_data.get("time_hours", 0))
                msg = func_data.get("message", "Reminder!")
                if hours <= 0:
                    return "Error: Reminder time must be positive."
                task = asyncio.create_task(remind_me(channel, user, hours, msg))
                scheduled_tasks[task] = (user, channel, msg)
                logger.info(f"Scheduled reminder for {user} in {hours} hours: {msg}")
                return f"Reminder set for {hours} hours from now: {msg}"
            else:
                logger.warning(f"Unknown function: {function_name}")
                return "Error: Unknown function requested."
        except (json.JSONDecodeError, ValueError) as e:
            logger.error(f"Failed to parse function call JSON: {str(e)}")
            return "Error: Invalid function call format."
    return None

# Store conversation history
class ConversationHistory:
    def __init__(self):
        self.messages = []
        self.last_reset = datetime.now()

    def add_message(self, content, author, timestamp):
        self.messages.append({
            'content': content,
            'author': str(author),
            'timestamp': timestamp
        })
        logger.debug(f"Added message to history - Author: {author}, Content: {content}")

    def reset_if_needed(self):
        now = datetime.now()
        if now - self.last_reset >= timedelta(days=1):
            logger.info("Resetting conversation history")
            self.messages = []
            self.last_reset = now

    def get_context(self):
        self.reset_if_needed()
        context = "\n".join([f"{msg['author']}: {msg['content']}" 
                           for msg in self.messages[-50:]])
        logger.debug(f"Generated context (last 50 messages):\n{context}")
        return context

history = ConversationHistory()

async def stream_llm_response(prompt, context, channel, user):
    async with channel.typing():
        try:
            logger.info(f"Processing prompt: {prompt}")
            logger.debug(f"Full context being sent to LLM:\n{context}")
            
            # Add current date and time to system prompt
            current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC")
            system_prompt = f"{SYSTEM_PROMPT_BASE}\nCurrent date and time: {current_time}"
            
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Context:\n{context}\n\nCurrent message: {prompt}"}
            ]
            logger.debug(f"Full message payload to LLM: {messages}")
            
            response = await openai.ChatCompletion.acreate(
                model=MODEL,
                messages=messages,
                max_tokens=500,
                stream=True
            )
            
            message = None
            full_response = ""
            using_embed = False
            
            logger.debug("Starting to stream response")
            async for chunk in response:
                logger.debug(f"Raw chunk received: {chunk}")
                chunk_text = chunk['choices'][0]['delta'].get('content', '')
                logger.debug(f"Extracted chunk text: '{chunk_text}'")
                full_response += chunk_text
                
                if len(full_response) > 200 or (chunk_text.endswith(('.', '!', '?')) and full_response):
                    if len(full_response) > EMBED_THRESHOLD and not using_embed:
                        if message is not None:
                            await message.delete()
                            logger.debug("Deleted initial plain text message to switch to embed")
                        embed = discord.Embed(description=full_response, color=discord.Color.blue())
                        embed.set_footer(text="Generated by Bot")
                        message = await channel.send(embed=embed)
                        using_embed = True
                        logger.debug(f"Sent initial embed: {full_response}")
                    elif using_embed:
                        embed = discord.Embed(description=full_response, color=discord.Color.blue())
                        embed.set_footer(text="Generated by Bot")
                        await message.edit(embed=embed)
                        logger.debug(f"Edited embed: {full_response}")
                    else:
                        if message is None:
                            message = await channel.send(full_response)
                            logger.debug(f"Sent initial message: {full_response}")
                        else:
                            await message.edit(content=full_response)
                            logger.debug(f"Edited message: {full_response}")
                    await asyncio.sleep(0.1)
            
            if full_response:
                func_response = await process_function_call(channel, user, full_response)
                if func_response:
                    if message is None:
                        message = await channel.send(func_response)
                    else:
                        await message.edit(content=func_response)
                    logger.debug(f"Function response sent: {func_response}")
                elif len(full_response) > EMBED_THRESHOLD:
                    if not using_embed and message is not None:
                        await message.delete()
                        logger.debug("Deleted final plain text message to switch to embed")
                    embed = discord.Embed(description=full_response, color=discord.Color.blue())
                    embed.set_footer(text="Generated by Bot")
                    if message is None or not using_embed:
                        message = await channel.send(embed=embed)
                    else:
                        await message.edit(embed=embed)
                    logger.debug(f"Final edit with embed: {full_response}")
                else:
                    if message is None:
                        message = await channel.send(full_response)
                    else:
                        await message.edit(content=full_response)
                    logger.debug(f"Final edit: {full_response}")
            else:
                logger.warning("No response content received from stream")
                message = await channel.send("No response generated.")
                
            logger.info("Response streaming completed")
            return message
        except Exception as e:
            logger.error(f"Error in stream_llm_response: {str(e)}", exc_info=True)
            error_msg = f"Error: {str(e)}"
            return await channel.send(error_msg)

def generate_invite_link(bot_id):
    permissions = discord.Permissions(
        read_messages=True,
        send_messages=True,
        read_message_history=True
    )
    return f"https://discord.com/oauth2/authorize?client_id={bot_id}&permissions={permissions.value}&scope=bot"

@bot.event
async def on_ready():
    logger.info(f'Bot connected as {bot.user}')
    logger.info(f'Using API endpoint: {API_URL}')
    logger.info(f'Using model: {MODEL}')
    logger.info(f'Using system prompt base: {SYSTEM_PROMPT_BASE}')
    logger.info(f'Logging level set to: {log_level}')
    invite_link = generate_invite_link(bot.user.id)
    logger.info(f"Bot invite link: {invite_link}")

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return

    logger.debug(f"Received message - Author: {message.author}, Content: {message.content}")
    history.add_message(message.content, message.author, datetime.now())

    if bot.user.mentioned_in(message):
        logger.info(f"Bot mentioned by {message.author}: {message.content}")
        context = history.get_context()
        await stream_llm_response(message.content, context, message.channel, message.author)
        return

    content = message.content.lower()
    should_respond = (
        '?' in content or
        'hey bot' in content or
        'what do you think' in content or
        len(content) > 20
    )

    if should_respond:
        logger.info(f"Bot triggered to respond to {message.author}: {message.content}")
        context = history.get_context()
        await stream_llm_response(message.content, context, message.channel, message.author)

# Main entry point
if __name__ == "__main__":
    try:
        logger.debug("Starting bot")
        bot.run(DISCORD_TOKEN)
    except Exception as e:
        logger.error(f"Failed to start bot: {str(e)}", exc_info=True)
