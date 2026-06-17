import os
import json
import asyncio
from pathlib import Path

import discord
from discord.ext import commands

TOKEN = os.getenv("DISCORD_TOKEN")

TICKET_PANEL_CHANNEL_ID = int(os.getenv("TICKET_PANEL_CHANNEL_ID", "1516534368225591386"))
TICKET_LOG_CHANNEL_ID = int(os.getenv("TICKET_LOG_CHANNEL_ID", "1516617002205319239"))

TICKET_SUPPORT_ROLE_ID = int(os.getenv("TICKET_SUPPORT_ROLE_ID", "1505906083812737134"))
TICKET_CLOSE_ROLE_ID = int(os.getenv("TICKET_CLOSE_ROLE_ID", "1516627835538903140"))

# Roluri care NU trebuie sa vada canalele ticket.
# ATENTIE: daca rolul are Administrator, Discord ignora permisiunile canalului.
TICKET_DENY_ROLE_IDS = [
    int(role_id.strip())
    for role_id in os.getenv("TICKET_DENY_ROLE_IDS", "1516635039520260186").split(",")
    if role_id.strip().isdigit()
]

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


def can_staff_take_ticket(member: discord.Member) -> bool:
    return has_role(member, TICKET_SUPPORT_ROLE_ID) or has_role(member, TICKET_CLOSE_ROLE_ID)


def safe_channel_name(name: str) -> str:
    clean = name.lower()
    allowed = "abcdefghijklmnopqrstuvwxyz0123456789-_"
    clean = "".join(ch if ch in allowed else "-" for ch in clean)
    while "--" in clean:
        clean = clean.replace("--", "-")
    return clean.strip("-")[:30] or "user"


def get_ticket_record_by_channel(channel_id: int) -> tuple[str | None, dict | None]:
    for user_id, value in active_tickets.items():
        if isinstance(value, dict):
            if str(value.get("channel_id")) == str(channel_id):
                return user_id, value
        else:
            # Compatibilitate cu versiunea veche: user_id -> channel_id
            if str(value) == str(channel_id):
                record = {"channel_id": str(value), "game_id": "", "taken_by": None}
                active_tickets[user_id] = record
                save_active_tickets(active_tickets)
                return user_id, record

    return None, None


async def send_log(guild: discord.Guild, embed: discord.Embed):
    log_channel = guild.get_channel(TICKET_LOG_CHANNEL_ID)

    if not isinstance(log_channel, discord.TextChannel):
        print(f"Eroare: canalul de log nu a fost gasit: {TICKET_LOG_CHANNEL_ID}")
        return

    try:
        await log_channel.send(embed=embed)
    except Exception as e:
        print(f"Eroare la trimiterea logului: {e}")


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
            "Un membru staff îți va răspunde în cel mai scurt timp posibil.\n\n"
            "🔒 Staff-ul poate vedea ticketul, dar poate scrie doar după ce apasă pe butonul **Preia Ticket**."
        ),
        color=discord.Color.green()
    )
    embed.add_field(name="ID jucător", value=f"`{game_id}`", inline=True)
    embed.add_field(name="Creat de", value=member.mention, inline=True)
    embed.set_footer(text="Doar staff-ul autorizat poate prelua / închide ticketul.")
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
    value = active_tickets.get(str(user_id))
    if not value:
        return

    if isinstance(value, dict):
        channel_id = value.get("channel_id")
    else:
        channel_id = value

    if not channel_id:
        active_tickets.pop(str(user_id), None)
        save_active_tickets(active_tickets)
        return

    channel = bot.get_channel(int(channel_id))
    if channel is None:
        active_tickets.pop(str(user_id), None)
        save_active_tickets(active_tickets)


def build_ticket_overwrites(
    guild: discord.Guild,
    ticket_owner: discord.Member,
    support_role: discord.Role,
    close_role: discord.Role
) -> dict:
    overwrites = {
        guild.default_role: discord.PermissionOverwrite(
            view_channel=False
        ),

        # Userul care a creat ticketul poate scrie mereu.
        ticket_owner: discord.PermissionOverwrite(
            view_channel=True,
            send_messages=True,
            read_message_history=True,
            attach_files=True,
            embed_links=True
        ),

        # Staff-ul vede ticketul, dar NU poate scrie pana nu apasa Preia Ticket.
        support_role: discord.PermissionOverwrite(
            view_channel=True,
            send_messages=False,
            read_message_history=True,
            attach_files=False,
            embed_links=False
        ),

        # Rolul de inchidere vede ticketul si poate apasa butoanele, dar nu scrie pana nu preia.
        close_role: discord.PermissionOverwrite(
            view_channel=True,
            send_messages=False,
            read_message_history=True,
            attach_files=False,
            embed_links=False
        ),

        guild.me: discord.PermissionOverwrite(
            view_channel=True,
            send_messages=True,
            read_message_history=True,
            manage_channels=True,
            manage_messages=True,
            attach_files=True,
            embed_links=True
        )
    }

    # Blocheaza explicit rolurile care nu trebuie sa vada ticketurile.
    # Daca acelasi rol este si support_role / close_role, nu il blocam.
    allowed_role_ids = {TICKET_SUPPORT_ROLE_ID, TICKET_CLOSE_ROLE_ID}
    for role_id in TICKET_DENY_ROLE_IDS:
        if role_id in allowed_role_ids:
            continue

        role = guild.get_role(role_id)
        if role:
            overwrites[role] = discord.PermissionOverwrite(
                view_channel=False,
                send_messages=False,
                read_message_history=False
            )

    return overwrites


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
            value = active_tickets[str(interaction.user.id)]
            channel_id = value.get("channel_id") if isinstance(value, dict) else value
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

        try:
            ticket_channel = await interaction.guild.create_text_channel(
                name=channel_name,
                category=category,
                overwrites=build_ticket_overwrites(
                    interaction.guild,
                    interaction.user,
                    support_role,
                    close_role
                ),
                topic=f"Ticket creat de {interaction.user} | UserID: {interaction.user.id} | GameID: {self.game_id.value}",
                reason=f"Ticket creat de {interaction.user}"
            )

            active_tickets[str(interaction.user.id)] = {
                "channel_id": str(ticket_channel.id),
                "game_id": str(self.game_id.value),
                "taken_by": None
            }
            save_active_tickets(active_tickets)

            await ticket_channel.send(
                content=f"{interaction.user.mention} {support_role.mention}",
                embed=build_ticket_embed(interaction.user, str(self.game_id.value)),
                view=TicketControlView()
            )

            log_embed = discord.Embed(
                title="🎫 Ticket creat",
                description=(
                    f"Ticket creat de: {interaction.user.mention}\n"
                    f"Canal: {ticket_channel.mention}\n"
                    f"ID jucător: `{self.game_id.value}`"
                ),
                color=discord.Color.blue()
            )
            await send_log(interaction.guild, log_embed)

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


class TicketControlView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Preia Ticket",
        style=discord.ButtonStyle.success,
        emoji="✅",
        custom_id="bot_ticket:take_ticket"
    )
    async def take_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message(
                "❌ Această acțiune poate fi folosită doar pe server.",
                ephemeral=True
            )
            return

        if not can_staff_take_ticket(interaction.user):
            await interaction.response.send_message(
                "❌ Nu ai permisiunea să preiei acest ticket.",
                ephemeral=True
            )
            return

        channel = interaction.channel
        if not isinstance(channel, discord.TextChannel):
            await interaction.response.send_message(
                "❌ Această acțiune poate fi folosită doar într-un canal ticket.",
                ephemeral=True
            )
            return

        owner_id, record = get_ticket_record_by_channel(channel.id)
        if record is None:
            await interaction.response.send_message(
                "❌ Acest canal nu este înregistrat ca ticket activ.",
                ephemeral=True
            )
            return

        if record.get("taken_by"):
            taken_member = interaction.guild.get_member(int(record["taken_by"]))
            taken_text = taken_member.mention if taken_member else f"`{record['taken_by']}`"
            await interaction.response.send_message(
                f"❌ Acest ticket este deja preluat de {taken_text}.",
                ephemeral=True
            )
            return

        try:
            # Doar adminul/staff-ul care a preluat primeste acces sa scrie.
            await channel.set_permissions(
                interaction.user,
                view_channel=True,
                send_messages=True,
                read_message_history=True,
                attach_files=True,
                embed_links=True,
                reason="Ticket preluat"
            )

            record["taken_by"] = str(interaction.user.id)
            active_tickets[str(owner_id)] = record
            save_active_tickets(active_tickets)

            await interaction.response.send_message(
                f"✅ Ticket preluat de {interaction.user.mention}."
            )

            log_embed = discord.Embed(
                title="✅ Ticket preluat",
                description=(
                    f"Ticket preluat de user: {interaction.user.mention}\n"
                    f"Canal: {channel.mention}\n"
                    f"Ticket creat de: <@{owner_id}>"
                ),
                color=discord.Color.green()
            )
            await send_log(interaction.guild, log_embed)

        except discord.Forbidden:
            await interaction.response.send_message(
                "❌ Botul nu are permisiuni pentru a modifica accesul la canal.",
                ephemeral=True
            )
        except Exception as e:
            await interaction.response.send_message(
                f"❌ Eroare la preluarea ticketului: `{e}`",
                ephemeral=True
            )

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

        owner_id, record = get_ticket_record_by_channel(channel.id)

        if owner_id:
            active_tickets.pop(owner_id, None)
            save_active_tickets(active_tickets)

        await interaction.response.send_message(
            f"🔒 Ticketul a fost închis de {interaction.user.mention}. "
            f"Canalul se va șterge în `{TICKET_DELETE_DELAY}` secunde."
        )

        log_embed = discord.Embed(
            title="🔒 Ticket închis",
            description=(
                f"Ticket închis de user: {interaction.user.mention}\n"
                f"Canal: `#{channel.name}`\n"
                f"Ticket creat de: {f'<@{owner_id}>' if owner_id else '`necunoscut`'}"
            ),
            color=discord.Color.red()
        )
        await send_log(interaction.guild, log_embed)

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
    bot.add_view(TicketControlView())

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


@bot.tree.command(name="ticket_fix_permissions", description="Repară permisiunile ticketurilor deschise.")
async def ticket_fix_permissions(interaction: discord.Interaction):
    if not isinstance(interaction.user, discord.Member) or not has_role(interaction.user, TICKET_CLOSE_ROLE_ID):
        await interaction.response.send_message(
            "❌ Nu ai permisiunea să folosești această comandă.",
            ephemeral=True
        )
        return

    support_role = interaction.guild.get_role(TICKET_SUPPORT_ROLE_ID)
    close_role = interaction.guild.get_role(TICKET_CLOSE_ROLE_ID)

    if support_role is None or close_role is None:
        await interaction.response.send_message(
            "❌ Rolurile configurate nu au fost găsite.",
            ephemeral=True
        )
        return

    fixed = 0

    for user_id, value in list(active_tickets.items()):
        if isinstance(value, dict):
            channel_id = value.get("channel_id")
            taken_by = value.get("taken_by")
        else:
            channel_id = value
            taken_by = None

        channel = interaction.guild.get_channel(int(channel_id))
        member = interaction.guild.get_member(int(user_id))

        if not isinstance(channel, discord.TextChannel) or member is None:
            continue

        try:
            overwrites = build_ticket_overwrites(
                interaction.guild,
                member,
                support_role,
                close_role
            )

            # Pastreaza accesul de scriere pentru staff-ul care deja a preluat ticketul.
            if taken_by:
                taken_member = interaction.guild.get_member(int(taken_by))
                if taken_member:
                    overwrites[taken_member] = discord.PermissionOverwrite(
                        view_channel=True,
                        send_messages=True,
                        read_message_history=True,
                        attach_files=True,
                        embed_links=True
                    )

            await channel.edit(
                overwrites=overwrites,
                reason="Fix permisiuni ticket"
            )
            fixed += 1
        except Exception:
            pass

    await interaction.response.send_message(
        f"✅ Permisiunile au fost reparate pentru `{fixed}` ticketuri.",
        ephemeral=True
    )


if not TOKEN:
    raise RuntimeError("Lipseste DISCORD_TOKEN in variabilele Railway.")

bot.run(TOKEN)
