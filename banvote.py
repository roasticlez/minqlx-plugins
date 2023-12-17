# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

# If you have any suggestions or issues/problems with this plugin you can contact me(kanzo) on irc at #minqlbot
# or alternatively you can open an issue at https://github.com/cstewart90/minqlx-plugins/issues

"""
Ban players from voting.
"""

import minqlx
import minqlx.database
import datetime
import time
import re
from operator import itemgetter

LENGTH_REGEX = re.compile(r"(?P<number>[0-9]+) (?P<scale>seconds?|minutes?|hours?|days?|weeks?|months?|years?)")
TIME_FORMAT = "%Y-%m-%d %H:%M:%S"
PLAYER_KEY = "minqlx:players:{}"


class banvote(minqlx.Plugin):
    database = minqlx.database.Redis

    def __init__(self):
        super().__init__()
        self.add_hook("vote_called", self.handle_vote_called, priority=minqlx.PRI_HIGH)
        self.add_command("banvote", self.cmd_banvote, 2, usage="<id> <length> seconds|minutes|hours|days|... [reason]")
        self.add_command("unbanvote", self.cmd_unbanvote, 2, usage="<id>")
        self.add_command(("votebanned"), self.cmd_votebanned, 4)

    def handle_vote_called(self, player, vote, args):
        """Stops a banned player from voting."""
        votebanned = self.is_votebanned(player.steam_id)
        if votebanned:
            expires, reason = votebanned
            if reason:
                player.tell("You are banned from voting until {}: {}".format(expires, reason))
                return minqlx.RET_STOP_ALL
            else:
                player.tell("You are banned from voting until {}.".format(expires))
                return minqlx.RET_STOP_ALL

    def cmd_banvote(self, player, msg, channel):
        """Bans a player from voting."""
        if len(msg) < 4:
            return minqlx.RET_USAGE               
        
        try:            
            ident = int(msg[1])
            target_player = None
            
            if 0 <= ident < 64:                
                target_player = self.player(ident)                
                ident = target_player.steam_id            
            
        except ValueError:
            channel.reply("Invalid ID. Use either a client ID or a SteamID64.")
            return
        except minqlx.NonexistentPlayerError:
            channel.reply("Invalid client ID. Use either a client ID or a SteamID64.")
            return        
        
        if target_player:
            name = target_player.name
        else:
            name = ident                

        # Players with permissions level 1 or higher cannot be banned from voting.        
        if self.db.has_permission(ident, 1):
            channel.reply("^7{} ^3has permission level 1 or higher and cannot be banned from voting.".format(name))
            return              
            
        if len(msg) > 4:
            reason = " ".join(msg[4:])
        else:
            reason = ""        
        
        r = LENGTH_REGEX.match(" ".join(msg[2:4]).lower())
        if r:
            number = float(r.group("number"))
            if number <= 0: return
            scale = r.group("scale").rstrip("s")
            td = None            
            
            if scale == "second":
                td = datetime.timedelta(seconds=number)
            elif scale == "minute":
                td = datetime.timedelta(minutes=number)
            elif scale == "hour":
                td = datetime.timedelta(hours=number)
            elif scale == "day":
                td = datetime.timedelta(days=number)
            elif scale == "week":
                td = datetime.timedelta(weeks=number)
            elif scale == "month":
                td = datetime.timedelta(days=number * 30)
            elif scale == "year":
                td = datetime.timedelta(weeks=number * 52)                                                  
            
            now = datetime.datetime.now().strftime(TIME_FORMAT)
            expires = (datetime.datetime.now() + td).strftime(TIME_FORMAT)                 
            base_key = PLAYER_KEY.format(ident) + ":votebans"            
            voteban_id = self.db.zcard(base_key)            
            db = self.db.pipeline()            
            db.zadd(base_key, time.time() + td.total_seconds(), voteban_id)            
            voteban = {"expires": expires, "reason": reason, "issued": now, "issued_by": player.steam_id}            
            db.hmset(base_key + ":{}".format(voteban_id), voteban)            
            db.execute()            

            channel.reply("^7{} ^1has been banned from voting. Ban expires on ^6{}^7.".format(name, expires))

    def cmd_unbanvote(self, player, msg, channel):
        """Unbans a player from voting."""
        if len(msg) < 2:
            return minqlx.RET_USAGE

        try:
            ident = int(msg[1])
            target_player = None            
            if 0 <= ident < 64:
                target_player = self.player(ident)
                ident = target_player.steam_id                
            
        except ValueError:
            channel.reply("Invalid ID. Use either a client ID or a SteamID64.")
            return
        except minqlx.NonexistentPlayerError:
            channel.reply("Invalid client ID. Use either a client ID or a SteamID64.")
            return
        
        
        if target_player:
            name = target_player.name
        else:
            name = ident

        base_key = PLAYER_KEY.format(ident) + ":votebans"
        votebans = self.db.zrangebyscore(base_key, time.time(), "+inf", withscores=True)
        if not votebans:
            channel.reply("^7 No active banvotes on ^6{}^7 found.".format(name))
        else:
            db = self.db.pipeline()
            for voteban_id, score in votebans:
                db.zincrby(base_key, voteban_id, -score)
            db.execute()
            channel.reply("^6{}^7 has been unbanned from voting.".format(name))

    def cmd_votebanned(self, player, msg, channel):        
        """Outputs all votebanned players."""
        @minqlx.thread
        def votebans():            
            players = []
            for key in self.db.scan_iter("minqlx:players:765*:votebans"):                
                steam_id = key.split(":")[2]                                
                votebanned = self.is_votebanned(steam_id)                
                expires = votebanned[0]
                reason = votebanned[-1]
                name = self.player_name(steam_id)                                    
                players.append(dict(name=name, steam_id=steam_id, expires=str(expires), reason=reason))                
                        
            if players:                
                output = ["^5{:^31} | {:^17} | {:^19} | {}".format("Name", "Steam ID", "Expires", "Reason")]
                for p in sorted(players, key=itemgetter("expires")):
                    output.append("{name:31} | {steam_id:17} | {expires:19} | {reason}".format(**p))
                self.callback(player, command, output)
            else:
                self.callback(player, command, [])

        command = msg[0][1:].lower()
        votebans()
        return minqlx.RET_STOP_ALL

    # ====================================================================
    #                               HELPERS
    # ====================================================================

    def is_votebanned(self, steam_id):
        
        base_key = PLAYER_KEY.format(steam_id) + ":votebans"
        votebans = self.db.zrangebyscore(base_key, time.time(), "+inf", withscores=True)
        if not votebans:
            return None

        longest_voteban = self.db.hgetall(base_key + ":{}".format(votebans[-1][0]))
        expires = datetime.datetime.strptime(longest_voteban["expires"], TIME_FORMAT)
        if (expires - datetime.datetime.now()).total_seconds() > 0:
            return expires, longest_voteban["reason"]
        
        return None   

    @staticmethod
    def callback(player, command, output):
        """Tells player the output of the command.
        If player is a DummyPlayer then decreases max_amount and
        delay as to not disconnect the bot from IRC due to flooding."""
        if output:            
            if isinstance(player, minqlx.AbstractDummyPlayer):
                tell_large_output(player, output, max_amount=1, delay=2)
            else:
                tell_large_output(player, output)
        else:
            if command == "permissions":
                player.tell("There are no players with >= 1 permission level.")
            else:
                player.tell("There are no {} players.".format(command))

    def player_name(self, steam_id):
        """Returns the latest name a player has used."""
        try:
            name = self.db.lindex(PLAYER_KEY.format(steam_id), 0)
            if not name:
                raise KeyError
            name = re.sub(r"\^[0-9]", "", name)  # remove colour tags
        except KeyError:
            name = steam_id
        return name

def tell_large_output(player, output, max_amount=25, delay=0.4):
    """Tells large output in small portions, as not to disconnected the player.
    :param player: Player to tell to.
    :param output: Output to send to player.
    :param max_amount: Max amount of lines to send at once.
    :param delay: Time to sleep between large inputs.
    """
    for count, line in enumerate(output, start=1):
        if count % max_amount == 0:
            time.sleep(delay)
        player.tell(line)

