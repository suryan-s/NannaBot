"""
This is the main file for the bot operations
"""
import asyncio

import discord
from discord.ext import commands
from dotenv import load_dotenv
import os
import knowledge
from mysql.connector import pooling

load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')

intents = discord.Intents.default()
intents.members = True
intents.messages = True
intents.message_content = True

bot = commands.Bot(command_prefix='!', intents=intents)

config = {
    'user': os.getenv('DB_USERNAME'),
    'password': os.getenv('DB_PASSWORD'),
    'host': os.getenv('DB_HOST'),
    'port': os.getenv('DB_PORT'),
    'database': os.getenv('DB_DATABASE'),
}

connection_pool = pooling.MySQLConnectionPool(pool_name='my_pool', pool_size=32, **config)
chatbot = knowledge.initiate_chat()


@bot.event
async def on_ready():
    """
    This function is called when the bot is ready to start
    """
    await bot.change_presence(
        status=discord.Status.online,
        activity=discord.Activity(
            type=discord.ActivityType.listening,
            name="!help"
        )
    )
    try:
        com_sync = await bot.tree.sync()
        print("Synced commands: ", len(com_sync))
    except Exception as e:
        print(e)

    print(f'{bot.user.name} has connected to Discord!')


@bot.event
async def on_command_error(ctx, error):
    """
    This function is called when an error occurs while executing a command
    :param ctx:
    :param error:
    """
    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.send('Please pass in the required argument')
    elif isinstance(error, commands.CommandNotFound):
        await ctx.send('Invalid command')
    elif isinstance(error, commands.MissingPermissions):
        await ctx.send('You do not have the required permissions')


@bot.event
async def on_guild_join(guild):
    """
    This function is called when the bot joins a server
    :param guild:
    """
    channel = guild.text_channels[0]
    embed = discord.Embed(title=guild.name, description="Hello, I'm Nanna the bot!")
    await channel.send(embed=embed)


@bot.event
async def on_guild_remove(guild):
    """
    This function is called when the bot is removed from a server
    :param guild:
    :return:
    """
    channel = guild.text_channels[0]
    embed = discord.Embed(title=guild.name, description="Goodbye :( ")
    await channel.send(embed=embed)


@bot.event
async def on_member_join(member):
    """
    This function is called when a member joins the server
    :param member:
    """
    guild = member.guild
    channel = guild.text_channels[0]
    embed = discord.Embed(title=member.name, description="Welcome to the server! :heart:")
    await channel.send(embed=embed)
    dm = await member.create_dm()
    await dm.send(
        f'**Hi {member.name}**,\nWelcome to the {guild} server :wave:\nPls go through the **rules channel** and have fun!'
    )


@bot.event
async def on_member_remove(member):
    """
    This function is called when a member leaves the server
    :param member:
    """
    # print(f'{member} left the server.')
    guild = member.guild
    channel = guild.text_channels[0]
    embed = discord.Embed(title=member.name, description="left the server. Goodbye :disappointed:")
    await channel.send(embed=embed)


@bot.command()
async def ping(ctx):
    """
    This function is called when the user sends a ping command
    :param ctx:
    """
    await ctx.send(f'Pong! {round(bot.latency * 1000)}ms')


@bot.event
async def on_message(message):
    """
    This function is called when a webhook payload is received.
    :param message:
    :return:
    """
    await bot.process_commands(message)

    if message.author == bot.user:
        return

    if message.webhook_id is not None:
        guild = message.guild
        channel = guild.text_channels[0]
        data = message.content.split('|')
        if data[0] == 'role':
            new_role = await guild.create_role(name=data[1])
            permissions = discord.Permissions()
            permissions.update(
                read_messages=True,
                read_message_history=True,
                send_messages=True
            )
            await new_role.edit(permissions=permissions)
            await channel.send(f"Role created : {new_role.name}")

        elif data[0] == 'channel':
            new_channel = await guild.create_text_channel(name=data[1])
            everyone_role = discord.utils.get(guild.roles, name="@everyone")
            await new_channel.set_permissions(
                everyone_role,
                send_messages=True,
                view_channel=True,
                manage_channels=False,
                manage_messages=False
            )
            # await channel.send(f"Channel created : {new_channel.name}")


# @bot.tree.command(name="discord_to_db")
async def discord_to_db(interaction: discord.Interaction):
    """
    This function is called when the user wants to sync the details from discord to the database
    """
    guild_update = False

    connection = connection_pool.get_connection()
    cursor = connection.cursor()
    guild_id = interaction.guild_id
    guild_name = interaction.guild.name
    guild = interaction.guild

    role_info = []
    await interaction.response.defer()
    for role in guild.roles:
        role_info.append(
            (str(role.id), str(role.name), str(role.permissions.value), str(guild_id))
        )
    try:
        query1 = """SELECT * FROM guild WHERE guild_id = %s"""
        values1 = (guild_id,)
        cursor.execute(query1, values1)
        result1 = cursor.fetchall()
        if len(result1) == 0:
            # print("No guild found")
            guild_update = True
            query2 = """
            INSERT INTO guild(guild_id, guild_name) VALUES (%s, %s)
            """
            values2 = (str(guild_id), str(guild_name))
            cursor.execute(query2, values2)
            connection.commit()
            # print("Guild added to database")
        else:
            # print("Guild found")
            query3 = """
            DELETE FROM roles WHERE guild_id = %s
            """
            values3 = (str(guild_id),)
            cursor.execute(query3, values3)
            connection.commit()

        query4 = """
        INSERT INTO roles(role_id, role_name, role_perm, guild_id) VALUES (%s, %s, %s, %s)
        """
        cursor.executemany(query4, role_info)
        connection.commit()
        cursor.close()
        if guild_update:
            await interaction.followup.send(
                f"{guild_name} registered successfully and synced to database"
            )
        else:
            await interaction.followup.send(
                f"{guild_name} data synced with database"
            )
    except Exception as e:
        print(e)
        connection.rollback()
        cursor.close()
        await interaction.followup.send(
            "Error syncing database to discord"
        )
        return


# @bot.tree.command(name="db_to_discord")
async def db_to_discord(interaction: discord.Interaction):
    """
    This function is called when the user wants to sync the details from database to discord
    """
    discord_update = False

    connection = connection_pool.get_connection()
    cursor = connection.cursor()
    guild_id = interaction.guild_id
    guild_name = interaction.guild.name
    guild = interaction.guild

    try:
        query = """SELECT role_id, role_name, role_perm from roles WHERE guild_id = %s"""
        values = (guild_id,)
        cursor.execute(query, values)
        result1 = cursor.fetchall()
        if len(result1) == 0:
            await interaction.response.send_message(
                f"{guild_name} was never synced with database. Please sync with database"
            )
            return
        else:
            await interaction.response.defer()
            for data in result1:
                role_id, role_name, role_permissions = data
                role = guild.get_role(int(role_id))
                if role:
                    await role.edit(name=role_name, permissions=discord.Permissions(int(role_permissions)))
                    # print("Role %s updated" % role_name)
            discord_update = True
        if discord_update:
            await interaction.followup.send(
                f"Database synced with {guild_name}"
            )
        else:
            await interaction.followup.send(
                "Error syncing. Please try again"
            )
            return
    except discord.Forbidden:
        await interaction.followup.send(
            f"Sorry I couldn't sync with database as I don't have the right permissions in {guild_name}"
        )
        return
    except Exception as e:
        print("Exception: ", e)
        connection.rollback()
        cursor.close()
        await interaction.followup.send(
            f"Error syncing database with {guild_name}"
        )
        return


@bot.tree.command(
    name="sync_guild",
    description="Sync the guild details from database to discord or vice versa. Default is discord to database",
)
async def sync_guild(interaction: discord.Interaction, db_to_dc: bool = False):
    """
    This function is called when the user wants to sync the details.
    Default is discord to database sync but
    can be changed to a database to discord sync.

    The operations are performed by separate functions based on the parameter passed:
    db_to_discord: for database to discord sync,
    discord_to_db: for discord to database sync.

    :param interaction: The interaction object that is passed by the user
    :param db_to_dc: True if a database to discord sync is required.
                    False if discord to database sync is required
    """
    if db_to_dc:
        await db_to_discord(interaction)
    else:
        await discord_to_db(interaction)


@bot.tree.command(
    name="ask-me",
    description="Ask me anything and if i dont know it, teach me",
)
async def ask_me(interaction: discord.Interaction, question: str):
    """
    This function is called when the user wants to ask a question to the bot.
    :param interaction:
    :param question:
    :return:
    """
    brain = knowledge.load_knowledge()
    global chatbot
    try:
        await interaction.response.defer()
        if question is None or question == "":
            await interaction.followup.send("No question was asked. Please ask a question")
            return
        question = question.lower()
        best_match: str | None = knowledge.find_answer(question, chatbot)
        if best_match is not None:
            if best_match is None or best_match == "":
                await interaction.followup.send('I dont know the answer, please teach me the answer')
                user_response = await bot.wait_for(
                    'message',
                    check=lambda message: message.author == interaction.user, timeout=60
                )
                await interaction.followup.send(f'Thanks for teaching me the answer. I will remember it')
                brain['questions'].append({'question': question, 'answer': user_response.content})
                knowledge.save_knowledge(brain)
                chatbot = knowledge.initiate_chat()
                return
            await interaction.followup.send(best_match)
        else:
            await interaction.followup.send('I dont know the answer, please teach me the answer')
            user_response = await bot.wait_for(
                'message',
                check=lambda message: message.author == interaction.user, timeout=60
            )
            await interaction.followup.send(f'Thanks for teaching me the answer. I will remember it')
            brain['questions'].append({'question': question, 'answer': user_response.content})
            knowledge.save_knowledge(brain)
            chatbot = knowledge.initiate_chat()
    except asyncio.TimeoutError:
        await interaction.followup.send('Sorry you took too long to answer')
        return


bot.run(TOKEN)