FROM alpine:3.20 AS builder

RUN apk add --no-cache git build-base pcre-dev zlib-dev openssl-dev wget

WORKDIR /build

RUN git clone --depth 1 https://github.com/arut/nginx-rtmp-module.git && \
    wget https://nginx.org/download/nginx-1.27.2.tar.gz && \
    tar -xzf nginx-1.27.2.tar.gz

WORKDIR /build/nginx-1.27.2

RUN ./configure \
      --with-http_ssl_module \
      --add-module=../nginx-rtmp-module \
      --prefix=/usr/local/nginx \
      --with-cc-opt="-O2" && \
    make -j$(nproc) && \
    make install && \
    strip /usr/local/nginx/sbin/nginx

FROM alpine:3.20

RUN apk add --no-cache pcre zlib openssl

RUN addgroup -S nginx && adduser -S nginx -G nginx

COPY --from=builder /usr/local/nginx /usr/local/nginx
COPY ./config/ /etc/nginx/
COPY ./html/ /usr/share/nginx/html/

RUN mkdir -p /var/log/nginx && chown -R nginx:nginx /var/log/nginx

CMD ["/usr/local/nginx/sbin/nginx", "-c", "/etc/nginx/nginx.conf", "-g", "daemon off;"]