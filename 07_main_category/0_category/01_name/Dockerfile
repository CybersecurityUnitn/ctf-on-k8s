# Make the /app directory not writeable
RUN chmod a-w /app

# Create a nonroot user
RUN adduser -D nonroot && \
    chown nonroot /app

# Make the /static directory writeable
RUN mkdir /app/static && \
    chown nonroot /app/static

# ! Important: install the required packages before switching the user

# Switch to the nonroot user before executing the CMD
USER nonroot
