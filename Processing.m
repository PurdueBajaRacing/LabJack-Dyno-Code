T = readmatrix("data/LJdata23.csv");

actualScanRate = 25000;

timestamps = T(:,1);
timestamps(2:2:end) = timestamps(2:2:end) - .00005;
torques = T(:,2);
shaft_speed = T(:,3);
raw_engine_rpm = T(:,4);

window_size = (actualScanRate/10); % Smoothing constant
disp("Smoothing Torque...")
torque_smooth = smoothdata(torques, 'movmean', window_size);

raw_engine_rpm(1) = 0;

raw_engine_rpm(raw_engine_rpm > 120000) = NaN;
raw_engine_rpm(raw_engine_rpm < 0) = NaN;

window_size = (actualScanRate/25); % Smoothing constant
engine_rpm = smoothdata(raw_engine_rpm, 'movmean', window_size, 'omitnan');

% cvt_ratio = engine_rpm ./ shaft_speed;

% --- Export to CSV ---
% Create a table with descriptive column names
outputTable = table(timestamps, engine_rpm, shaft_speed, torques, torque_smooth, ...
    'VariableNames', {'Timestamp_s', 'Engine_RPM', 'Shaft_Speed_RPM', 'Raw Torque Ft-Lbs', 'Torque_FtLbs'});

% Write the table to a CSV file
writetable(outputTable, 'Processed_LJdata.csv');

figure;
grid on;
hold on;
% scatter(timestamps, engine_rpm, "yellow");
% scatter(timestamps, shaft_speed, "blue");
plot(timestamps, engine_rpm, "y-");
plot(timestamps, shaft_speed, "b-");
xlabel("Time (s)");
ylabel("Speed (RPM)");
yyaxis right
% scatter(timestamps, torque_smooth, "red");
plot(timestamps, torque_smooth, "r-");
legend("Engine RPM", "Shaft Speed", "Torque");
ylabel("Torque (Ft-Lbs)");
hold off;