This bot is essentially a chatbot that uses large language models that are OpenAI API compatible.

## Features

- **Automated Responses**: Provides intelligent and context-aware responses to user queries.
- **Reminder Functionality**: Allows users to set reminders that the bot will notify them about.
- **Contextual Awareness**: Maintains conversation context to provide more relevant responses.
- **Streaming Responses**: Streams responses from the language model for a more interactive experience.

## Docker Compose

To build and run the bot using Docker Compose, follow these steps:

1. **Create a `docker-compose.yml` file** with the following content:

    ```yaml
    services:
      discord-llm-bot:
        image: ghcr.io/sourcequality/discordllmbot:main
        environment:
          - DISCORD_TOKEN=#YOURDISCORDTOKEN
          - API_KEY=#YOURAPIKEY
          - API_URL="https://api.openai.com/v1" # Defaults to https://api.openai.com/v1
          - SYSTEM_PROMPT="You are a Discord chatbot, respond in short messages."
          - MODEL=#MODEL NAME
          - LOG_LEVEL=#INFO/DEBUG
        restart: unless-stopped
    ```

2. **Run the Docker container**:

    ```sh
    docker-compose up
    ```

3. **Access the bot**: Once the container is running, the bot will be active and ready to respond to messages in your Discord server.

## Usage

To use the bot, invite it to your Discord server using the invite link generated in the logs when the bot starts. Mention the bot or use specific trigger phrases to interact with it.

## Contributing

We welcome contributions! Please fork the repository and submit a pull request with your changes.


## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.

