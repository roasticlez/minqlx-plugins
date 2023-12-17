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
        if self.db.has_permission(target_player.steam_id, 1):
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
