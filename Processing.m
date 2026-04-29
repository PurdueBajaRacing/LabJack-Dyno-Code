T = readmatrix("data/LJdata68.csv");

timestamps = T(:,1);
torques = T(:,2);
shaft_speed = T(:,3);
raw_engine_rpm = T(:,4);

window_size = 10; % Smoothing constant
torque_smooth = smoothdata(torques, 'movmean', window_size);

window_size = 25; % Smoothing constant
engine_rpm = smoothdata(raw_engine_rpm, 'movmean', window_size);

cvt_ratio = engine_rpm / shaft_speed;

figure;
grid on;
hold on;
scatter(timestamps, engine_rpm, "yellow");
scatter(timestamps, shaft_speed, "blue");
yyaxis right
scatter(timestamps, torque_smooth, "red");
legend("Engine RPM", "Shaft Speed", "Torque");
hold off;