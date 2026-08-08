FROM python:3.11-slim

ENV TZ=Asia/Kolkata
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV STRATEGY=hd,cd
ENV MODE=live

CMD ["sh", "-c", "exec python3 run_strategy.py --strategy $STRATEGY --mode $MODE"]
