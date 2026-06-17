import os
import json
import asyncio
from pathlib import Path

import discord
from discord.ext import commands

TOKEN = os.getenv("DISCORD_TOKEN")

TICKET_PANEL_CHANNEL_ID = int(os.getenv("TICKET_PANEL_CHANNEL_ID", "1516534368225591386"))
TICKET_SUPPORT_ROLE_ID = int(os.getenv("TICKET_SUPPORT_ROLE_ID", "1505906083812737134"))
TICKET_CLOSE_ROLE_ID = int(os.getenv("TICKET_CLOSE_ROLE_ID", "1516627835538903140"))

# 0 = foloseste aceeasi categorie unde se afla canalul panelului
TICKET_CATEGORY_ID = int(os.getenv("TICKET_CATEGORY_ID", "0"))

TICKET_CHANNEL_PREFIX = os.getenv("TICKET_CHANNEL_PREFIX", "ticket-suport")
TICKET_DELETE_DELAY = int(os.getenv("TICKET_DELETE_DELAY", "5"))

DATA_FILE = Path("active_tickets.json")

intents = discord.Intents.default()
intents.guilds = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)


def load_active_tickets() -> dict:
    if not DATA_FILE.exists():
        return {}

    try:
        return json.loads(DATA_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_active_tickets(data: dict):
    DATA_FILE.write_text(
        json.dumps(data, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )


active_tickets = load_active_tickets()


def has_role(member: discord.Member, role_id: int) -> bool:
    return any(role.id == role_id for role in member.roles)


def safe_channel_name(name: str) -> str:
    clean = name.lower()
    allowed = "abcdefghijklmnopqrstuvwxyz0123456789-_"
    clean = "".join(ch if ch in allowed else "-" for ch in clean)
    while "--" in clean:
        clean = clean.replace("--", "-")
    return clean.strip("-")[:30] or "user"


def build_panel_embed() -> discord.Embed:
    embed = discord.Embed(
        title="🎫 Sistem Ticket",
        description=(
            "Consideri că ai fost sancționat dintr-un motiv greșit sau un membru staff "
            "a vorbit urât / te-a insultat? Atunci creează un ticket pentru a reclama "
            "situația unui grad staff superior care te poate ajuta.\n\n"
            "⚠️ **Pentru orice reclamație este obligatoriu să ai dovezi audio-video / foto.**\n"
            "Asigură-te că ai dovezile pregătite înainte să deschizi ticketul. "
            "Dacă reclamația nu conține dovezi clare, aceasta nu va fi luată în considerare "
            "și ticketul poate fi închis.\n\n"
            "Ai o problemă cu jocul? Creează un ticket, explică motivul și trimite poze/video, "
            "iar noi vom încerca să te ajutăm în cel mai bun mod posibil."
        ),
        color=discord.Color.blue()
    )
    embed.set_footer(text="Apasă pe butonul de mai jos pentru a crea un ticket.")
    return embed


def build_ticket_embed(member: discord.Member, game_id: str) -> discord.Embed:
    embed = discord.Embed(
        title="🎫 Ticket Suport",
        description=(
            f"Salut {member.mention}, ticketul tău a fost creat.\n\n"
            "Te rugăm să descrii problema cât mai clar posibil.\n\n"
            "⚠️ **Dacă ticketul este o reclamație, este obligatoriu să trimiți dovezi audio-video / foto.**\n"
            "Orice reclamație fără dovezi clare nu va fi luată în considerare și poate fi închisă.\n\n"
            "Un membru staff îți va răspunde în cel mai scurt timp posibil."
        ),
        color=discord.Color.green()
    )
    embed.add_field(name="ID jucător", value=f"`{game_id}`", inline=True)
    embed.add_field(name="Creat de", value=member.mention, inline=True)
    embed.set_footer(text="Doar staff-ul autorizat poate închide ticketul.")
    return embed


async def get_ticket_category(guild: discord.Guild) -> discord.CategoryChannel | None:
    if TICKET_CATEGORY_ID:
        category = guild.get_channel(TICKET_CATEGORY_ID)
        if isinstance(category, discord.CategoryChannel):
            return category

    panel_channel = guild.get_channel(TICKET_PANEL_CHANNEL_ID)
    if isinstance(panel_channel, discord.TextChannel):
        return panel_channel.category

    return None


async def cleanup_missing_ticket(user_id: int):
    channel_id = active_tickets.get(str(user_id))
    if not channel_id:
        return

    channel = bot.get_channel(int(channel_id))
    if channel is None:
        active_tickets.pop(str(user_id), None)
        save_active_tickets(active_tickets)


class TicketIdModal(discord.ui.Modal, title="Creează Ticket"):
    game_id = discord.ui.TextInput(
        label="ID-ul tău din joc",
        placeholder="Exemplu: 123",
        required=True,
        max_length=30
    )

    async def on_submit(self, interaction: discord.Interaction):
        if not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message(
                "❌ Această acțiune poate fi folosită doar pe server.",
                ephemeral=True
            )
            return

        await cleanup_missing_ticket(interaction.user.id)

        if str(interaction.user.id) in active_tickets:
            channel_id = active_tickets[str(interaction.user.id)]
            channel = interaction.guild.get_channel(int(channel_id))
            if channel:
                await interaction.response.send_message(
                    f"❌ Ai deja un ticket deschis: {channel.mention}\n"
                    "Trebuie să fie închis înainte să poți crea altul.",
                    ephemeral=True
                )
                return

        support_role = interaction.guild.get_role(TICKET_SUPPORT_ROLE_ID)
        close_role = interaction.guild.get_role(TICKET_CLOSE_ROLE_ID)

        if support_role is None:
            await interaction.response.send_message(
                "❌ Eroare configurare: rolul staff pentru ticket nu a fost găsit.",
                ephemeral=True
            )
            return

        if close_role is None:
            await interaction.response.send_message(
                "❌ Eroare configurare: rolul care poate închide ticketul nu a fost găsit.",
                ephemeral=True
            )
            return

        category = await get_ticket_category(interaction.guild)
        channel_name = f"{TICKET_CHANNEL_PREFIX}-{safe_channel_name(interaction.user.name)}"

        overwrites = {
            interaction.guild.default_role: discord.PermissionOverwrite(
                view_channel=False
            ),
            interaction.user: discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True,
                attach_files=True,
                embed_links=True
            ),
            support_role: discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True,
                attach_files=True,
                embed_links=True
            ),
            close_role: discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True,
                attach_files=True,
                embed_links=True
            ),
            interaction.guild.me: discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True,
                manage_channels=True,
                manage_messages=True,
                attach_files=True,
                embed_links=True
            )
        }

        try:
            ticket_channel = await interaction.guild.create_text_channel(
                name=channel_name,
                category=category,
                overwrites=overwrites,
                topic=f"Ticket creat de {interaction.user} | UserID: {interaction.user.id} | GameID: {self.game_id.value}",
                reason=f"Ticket creat de {interaction.user}"
            )

            active_tickets[str(interaction.user.id)] = str(ticket_channel.id)
            save_active_tickets(active_tickets)

            await ticket_channel.send(
                content=f"{interaction.user.mention} {support_role.mention}",
                embed=build_ticket_embed(interaction.user, str(self.game_id.value)),
                view=CloseTicketView()
            )

            await interaction.response.send_message(
                f"✅ Ticketul tău a fost creat: {ticket_channel.mention}",
                ephemeral=True
            )

        except discord.Forbidden:
            await interaction.response.send_message(
                "❌ Botul nu are permisiuni suficiente pentru a crea canale.",
                ephemeral=True
            )
        except Exception as e:
            await interaction.response.send_message(
                f"❌ A apărut o eroare la crearea ticketului: `{e}`",
                ephemeral=True
            )


class TicketPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Creează Ticket",
        style=discord.ButtonStyle.primary,
        emoji="🎫",
        custom_id="bot_ticket:create_ticket"
    )
    async def create_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(TicketIdModal())


class CloseTicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Ticket terminat",
        style=discord.ButtonStyle.danger,
        emoji="🔒",
        custom_id="bot_ticket:close_ticket"
    )
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message(
                "❌ Această acțiune poate fi folosită doar pe server.",
                ephemeral=True
            )
            return

        if not has_role(interaction.user, TICKET_CLOSE_ROLE_ID):
            await interaction.response.send_message(
                "❌ Nu ai permisiunea să închizi acest ticket.",
                ephemeral=True
            )
            return

        channel = interaction.channel
        if not isinstance(channel, discord.TextChannel):
            await interaction.response.send_message(
                "❌ Această comandă poate fi folosită doar într-un canal ticket.",
                ephemeral=True
            )
            return

        for user_id, channel_id in list(active_tickets.items()):
            if str(channel.id) == str(channel_id):
                active_tickets.pop(user_id, None)
                save_active_tickets(active_tickets)
                break

        await interaction.response.send_message(
            f"🔒 Ticketul a fost închis de {interaction.user.mention}. "
            f"Canalul se va șterge în `{TICKET_DELETE_DELAY}` secunde."
        )

        await asyncio.sleep(TICKET_DELETE_DELAY)

        try:
            await channel.delete(reason=f"Ticket închis de {interaction.user}")
        except Exception:
            pass


async def send_or_find_panel():
    for guild in bot.guilds:
        panel_channel = guild.get_channel(TICKET_PANEL_CHANNEL_ID)

        if not isinstance(panel_channel, discord.TextChannel):
            print(f"Eroare: canalul panel ticket nu a fost gasit: {TICKET_PANEL_CHANNEL_ID}")
            continue

        try:
            async for message in panel_channel.history(limit=50):
                if message.author == bot.user and message.embeds:
                    if message.embeds[0].title == "🎫 Sistem Ticket":
                        try:
                            await message.edit(embed=build_panel_embed(), view=TicketPanelView())
                            print("Panel ticket existent actualizat.")
                            return
                        except Exception:
                            pass

            await panel_channel.send(embed=build_panel_embed(), view=TicketPanelView())
            print("Panel ticket trimis.")
        except discord.Forbidden:
            print("Eroare: botul nu poate trimite mesaje in canalul panel.")
        except Exception as e:
            print(f"Eroare la trimiterea panelului ticket: {e}")


@bot.event
async def on_ready():
    print(f"Bot Ticket online ca {bot.user} | Servere: {len(bot.guilds)}")

    bot.add_view(TicketPanelView())
    bot.add_view(CloseTicketView())

    try:
        await bot.tree.sync()
        print("Comenzile slash au fost sincronizate.")
    except Exception as e:
        print(f"Eroare sync slash commands: {e}")

    await send_or_find_panel()


@bot.tree.command(name="ticket_setup", description="Trimite sau actualizează mesajul principal pentru ticket.")
async def ticket_setup(interaction: discord.Interaction):
    if not isinstance(interaction.user, discord.Member):
        await interaction.response.send_message(
            "❌ Această comandă poate fi folosită doar pe server.",
            ephemeral=True
        )
        return

    if not has_role(interaction.user, TICKET_CLOSE_ROLE_ID):
        await interaction.response.send_message(
            "❌ Nu ai permisiunea să folosești această comandă.",
            ephemeral=True
        )
        return

    await interaction.response.defer(ephemeral=True)
    await send_or_find_panel()
    await interaction.followup.send("✅ Mesajul pentru ticket a fost trimis / actualizat.", ephemeral=True)


@bot.tree.command(name="ticket_status", description="Arată câte ticketuri sunt deschise.")
async def ticket_status(interaction: discord.Interaction):
    if not isinstance(interaction.user, discord.Member) or not has_role(interaction.user, TICKET_CLOSE_ROLE_ID):
        await interaction.response.send_message(
            "❌ Nu ai permisiunea să folosești această comandă.",
            ephemeral=True
        )
        return

    for user_id in list(active_tickets.keys()):
        await cleanup_missing_ticket(int(user_id))

    await interaction.response.send_message(
        f"✅ Ticketuri deschise: `{len(active_tickets)}`",
        ephemeral=True
    )


if not TOKEN:
    raise RuntimeError("Lipseste DISCORD_TOKEN in variabilele Railway.")

bot.run(TOKEN)
