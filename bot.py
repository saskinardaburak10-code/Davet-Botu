# -*- coding: utf-8 -*-
"""
Discord Davet (Invite) Kontrol Botu
------------------------------------
Özellikler:
  1) !davetkontrol <davet_linki_veya_kodu>  -> Verilen davetin geçerli olup olmadığını,
     hangi sunucuya ait olduğunu, kimin oluşturduğunu vb. gösterir.
  2) !davetlerim [@kullanıcı]  -> O kullanıcının (belirtilmezse komutu yazanın)
     sunucudaki davet linkleriyle şu ana kadar kaç kişi davet ettiğini gösterir.
  3) !davetliste -> Sunucudaki tüm davetleri ve kimin kaç kişi getirdiğini listeler.

Gereksinimler:
    pip install -U discord.py

Kurulum:
    1) https://discord.com/developers/applications adresinden bir bot oluşturun.
    2) Bot sekmesinde "SERVER MEMBERS INTENT" ve "MESSAGE CONTENT INTENT" seçeneklerini açın.
    3) Botu sunucunuza "Manage Server" (Sunucuyu Yönet) ve "Manage Guild"/"View Invites"
       yetkileriyle davet edin (davet linklerini görebilmesi için Sunucuyu Yönet gerekir).
    4) Aşağıdaki TOKEN değerini kendi bot tokeninizle değiştirin ya da
       DISCORD_BOT_TOKEN ortam değişkenini ayarlayın.
    5) python bot.py ile çalıştırın.
"""

import os
import discord
from discord.ext import commands

TOKEN = os.environ.get("DISCORD_BOT_TOKEN", "BURAYA_BOT_TOKENINI_YAZ")
PREFIX = "!"

intents = discord.Intents.default()
intents.members = True          # üye giriş/çıkışlarını ve davet takibini yapabilmek için
intents.message_content = True  # komutları okuyabilmek için

bot = commands.Bot(command_prefix=PREFIX, intents=intents)

# guild.id -> {invite_code: uses} şeklinde önbellek (davet sayılarını karşılaştırmak için)
invite_cache: dict[int, dict[str, int]] = {}


async def cache_guild_invites(guild: discord.Guild):
    """Bir sunucunun mevcut davetlerini önbelleğe alır."""
    try:
        invites = await guild.invites()
        invite_cache[guild.id] = {inv.code: inv.uses or 0 for inv in invites}
    except discord.Forbidden:
        invite_cache[guild.id] = {}


@bot.event
async def on_ready():
    print(f"{bot.user} olarak giriş yapıldı.")
    for guild in bot.guilds:
        await cache_guild_invites(guild)
    print("Tüm sunucuların davet önbelleği hazırlandı.")


@bot.event
async def on_invite_create(invite: discord.Invite):
    guild_cache = invite_cache.setdefault(invite.guild.id, {})
    guild_cache[invite.code] = invite.uses or 0


@bot.event
async def on_invite_delete(invite: discord.Invite):
    guild_cache = invite_cache.get(invite.guild.id, {})
    guild_cache.pop(invite.code, None)


@bot.event
async def on_member_join(member: discord.Member):
    """Yeni üye katıldığında hangi davetin kullanıldığını tespit eder."""
    guild = member.guild
    old_invites = invite_cache.get(guild.id, {})

    try:
        new_invites = await guild.invites()
    except discord.Forbidden:
        return

    used_invite = None
    for inv in new_invites:
        old_uses = old_invites.get(inv.code, 0)
        if (inv.uses or 0) > old_uses:
            used_invite = inv
            break

    await cache_guild_invites(guild)

    if used_invite and used_invite.inviter:
        channel = guild.system_channel
        if channel:
            await channel.send(
                f"👋 **{member.name}** sunucuya katıldı! "
                f"Davet eden: **{used_invite.inviter.name}** "
                f"(davet kodu: `{used_invite.code}`, toplam kullanım: {used_invite.uses})"
            )


@bot.command(name="davetkontrol")
async def davet_kontrol(ctx: commands.Context, davet: str):
    """Bir davet linkinin/kodunun geçerli olup olmadığını kontrol eder.
    Kullanım: !davetkontrol https://discord.gg/abcd1234  (ya da sadece kod)
    """
    code = davet.strip().split("/")[-1]

    try:
        invite = await bot.fetch_invite(code, with_counts=True, with_expiration=True)
    except discord.NotFound:
        await ctx.send(f"❌ `{code}` kodlu davet **geçersiz** veya süresi dolmuş.")
        return
    except discord.HTTPException as e:
        await ctx.send(f"⚠️ Davet kontrol edilirken bir hata oluştu: {e}")
        return

    embed = discord.Embed(
        title="✅ Davet Geçerli",
        color=discord.Color.green(),
    )
    embed.add_field(name="Sunucu", value=invite.guild.name if invite.guild else "Bilinmiyor", inline=True)
    embed.add_field(name="Davet Kodu", value=invite.code, inline=True)
    if invite.inviter:
        embed.add_field(name="Oluşturan", value=str(invite.inviter), inline=True)
    if invite.approximate_member_count is not None:
        embed.add_field(name="Üye Sayısı", value=str(invite.approximate_member_count), inline=True)
    if invite.approximate_presence_count is not None:
        embed.add_field(name="Çevrimiçi Üye", value=str(invite.approximate_presence_count), inline=True)
    if invite.expires_at:
        embed.add_field(name="Son Kullanma", value=invite.expires_at.strftime("%d.%m.%Y %H:%M"), inline=True)
    if invite.channel:
        embed.add_field(name="Kanal", value=str(invite.channel), inline=True)

    await ctx.send(embed=embed)


@bot.command(name="davetlerim")
async def davetlerim(ctx: commands.Context, uye: discord.Member = None):
    """Belirtilen kullanıcının (ya da komutu yazanın) bu sunucuda oluşturduğu davetlerle
    toplam kaç kişi getirdiğini gösterir.
    Kullanım: !davetlerim  veya  !davetlerim @kullanıcı
    """
    hedef = uye or ctx.author

    if not ctx.guild:
        await ctx.send("Bu komut yalnızca sunucu içinde kullanılabilir.")
        return

    try:
        invites = await ctx.guild.invites()
    except discord.Forbidden:
        await ctx.send("⚠️ Davetleri görüntüleme yetkim yok (Sunucuyu Yönet izni gerekiyor).")
        return

    kendi_davetleri = [inv for inv in invites if inv.inviter and inv.inviter.id == hedef.id]
    toplam_kullanim = sum(inv.uses or 0 for inv in kendi_davetleri)

    if not kendi_davetleri:
        await ctx.send(f"📭 **{hedef.display_name}** bu sunucuda aktif bir davet linki oluşturmamış.")
        return

    embed = discord.Embed(
        title=f"📨 {hedef.display_name} kullanıcısının davetleri",
        color=discord.Color.blurple(),
    )
    embed.add_field(name="Toplam Davet Edilen Kişi", value=str(toplam_kullanim), inline=False)
    embed.add_field(name="Aktif Davet Linki Sayısı", value=str(len(kendi_davetleri)), inline=False)

    detay = "\n".join(f"`{inv.code}` → {inv.uses or 0} kullanım" for inv in kendi_davetleri)
    embed.add_field(name="Detaylar", value=detay[:1024], inline=False)

    await ctx.send(embed=embed)


@bot.command(name="davetliste")
@commands.has_permissions(manage_guild=True)
async def davet_liste(ctx: commands.Context):
    """Sunucudaki tüm davetleri, oluşturan kişi ve kullanım sayısıyla listeler."""
    try:
        invites = await ctx.guild.invites()
    except discord.Forbidden:
        await ctx.send("⚠️ Davetleri görüntüleme yetkim yok (Sunucuyu Yönet izni gerekiyor).")
        return

    if not invites:
        await ctx.send("Bu sunucuda aktif davet linki bulunmuyor.")
        return

    invites_sirali = sorted(invites, key=lambda i: i.uses or 0, reverse=True)
    satirlar = [
        f"`{inv.code}` — {inv.inviter.name if inv.inviter else 'Bilinmiyor'} — {inv.uses or 0} kullanım"
        for inv in invites_sirali
    ]

    embed = discord.Embed(
        title=f"📋 {ctx.guild.name} — Davet Listesi",
        description="\n".join(satirlar)[:4000],
        color=discord.Color.gold(),
    )
    await ctx.send(embed=embed)


if __name__ == "__main__":
    if TOKEN == "MTU1MzY2ODg2NTI3ODM1MzQzOQ.GCYgmJ.Jkd8_ENwZ9Lmc8kisFvz4bFYpsnRMTP_LNHguE":
        print("UYARI: Lütfen bot.py içindeki TOKEN değerini kendi bot tokeninizle değiştirin")
        print("ya da DISCORD_BOT_TOKEN ortam değişkenini ayarlayın.")
    bot.run(TOKEN)
