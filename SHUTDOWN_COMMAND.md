# Shutdown Command Documentation

## Overview
The `/shutdown` command allows server administrators to gracefully shut down the bot when needed. This is useful for maintenance, testing, or when people running the bot are away and remote shutdown capability is needed.

## Usage

### Slash Command
```
/shutdown
```

## Permissions
- **Required:** Administrator permissions in the Discord server
- **Ephemeral Response:** Unauthorized attempts show an error message only visible to the user who tried the command

## Command Behavior

### Successful Shutdown (Admin Only)
When an administrator executes the command:
1. A confirmation message is sent showing who initiated the shutdown
2. The message displays: `🛑 **Bot shutting down...**` with the admin's mention
3. The bot logs the shutdown event with the admin's username and ID
4. The bot gracefully closes the connection to Discord

**Example response:**
```
🛑 **Bot shutting down...**

Initiated by: @AdminUser
```

### Unauthorized Attempt (Non-Admin)
When a non-administrator tries to execute the command:
1. An error message appears (ephemeral - only visible to that user)
2. The message states: `❌ You do not have permission to use this command. Only administrators can shut down the bot.`
3. The unauthorized attempt is logged as a warning

**Example response:**
```
❌ You do not have permission to use this command. Only administrators can shut down the bot.
```

## Logging

### Successful Shutdown
```
Shutdown command executed by admin {username} ({user_id}) in guild {guild_name}
```

### Unauthorized Attempt
```
Unauthorized shutdown attempt by {username} ({user_id}) in guild {guild_name}
```

### Errors
Any errors during shutdown are logged with full stack trace:
```
Error during shutdown command: {error_details}
Failed to send shutdown error message: {error_details}
```

## Implementation Details

### Permission Check
The command uses Discord.py's built-in permission system:
```python
interaction.user.guild_permissions.administrator
```

This checks if the user has the "Administrator" role/permission in the server where the command was executed.

### Graceful Shutdown
The command uses `await bot.close()` which:
- Closes the WebSocket connection gracefully
- Allows the bot to finish processing any ongoing tasks
- Cleans up resources properly
- Exits the bot process cleanly

### Error Handling
The implementation includes:
- Permission validation before any action
- Try-catch block for shutdown errors
- Secondary error handler for message sending failures
- Comprehensive logging at all stages

## Examples

### Admin shutting down the bot
```
Admin: /shutdown
Bot: 🛑 **Bot shutting down...**
     Initiated by: @AdminUser
[Bot closes connection]
```

### Non-admin trying to use the command
```
User: /shutdown
Bot: ❌ You do not have permission to use this command. Only administrators can shut down the bot.
[Command fails, nothing happens]
```

## Testing the Command

To test the shutdown command:

1. **Ensure you have Administrator permissions** in your test server
2. **Run the bot** using the standard startup command
3. **Execute the command** using `/shutdown` in any channel
4. **Verify the bot responds** with the shutdown confirmation
5. **Check the logs** to confirm the shutdown was recorded

### Testing Unauthorized Access
1. Use a non-admin user account
2. Try executing `/shutdown`
3. Verify you receive the permission denied error

## Notes

- The command will be synced automatically with Discord when the bot starts (via `bot.tree.sync()`)
- The shutdown is instant - no countdown or confirmation dialog
- All in-flight requests will be interrupted when the bot closes
- This command is useful for testing scenarios where remote control is needed
