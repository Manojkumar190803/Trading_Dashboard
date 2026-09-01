FROM python:3.11-slim

ENV TZ=Asia/Kolkata
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY run_strategy.py .
COPY core ./core
RUN mkdir -p strategies
COPY strategies/base.py strategies/ema21.py ./strategies/

ENV STRATEGY=ema21
ENV MODE=live
ENV SCRIPT=NIFTY

CMD ["sh", "-c", "exec python3 run_strategy.py --script $SCRIPT --strategy $STRATEGY --mode $MODE"]
