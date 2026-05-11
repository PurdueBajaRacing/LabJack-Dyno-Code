T = readmatrix("data/LJdata3.csv");

actualScanRate = 25000;

timestamps = T(:,1);
timestamps(2:2:end) = timestamps(2:2:end) - .00005;
torques = T(:,2);
torques(abs(torques) > 73.96*1.5) = NaN;
shaft_speed = T(:,3);
shaft_speed(abs(shaft_speed) > 6000*1.5) = NaN;
raw_engine_rpm = T(:,4);

window_size = (actualScanRate/1000); % Smoothing constant
disp("Smoothing Torque...");
torque_smooth = smoothdata(torques, 'movmean', window_size, 'omitnan');

disp("Smoothing Shaft RPM...");
shaft_speed_smooth = smoothdata(shaft_speed, 'movmean', window_size, 'omitnan');

disp("Smoothing Engine RPM...");
raw_engine_rpm(1) = 0;

raw_engine_rpm(raw_engine_rpm > 120000) = NaN;
raw_engine_rpm(raw_engine_rpm < 0) = NaN;

window_size = (actualScanRate/50); % Smoothing constant
engine_rpm = smoothdata(raw_engine_rpm, 'movmean', window_size, 'omitnan');

% --- Export to CSV ---
% Create a table with descriptive column names
disp("Exporting to CSV...");
outputTable = table(timestamps, engine_rpm, shaft_speed, shaft_speed_smooth, torques, torque_smooth, ...
    'VariableNames', {'Timestamp (s)', 'Engine RPM', 'Raw Shaft RPM', 'Smooth Shaft RPM', 'Raw Torque (FtLbs)', 'Smooth Torque (FtLbs)'});

% Write the table to a CSV file
writetable(outputTable, 'Processed_LJdata.csv');

disp("Plotting...");
figure;
grid on;
hold on;
plot(timestamps, engine_rpm, "y-");
plot(timestamps, shaft_speed_smooth, "b-");
xlabel("Time (s)");
ylabel("Speed (RPM)");
yyaxis right
plot(timestamps, torque_smooth, "r-");
legend("Engine RPM", "Shaft Speed", "Torque");
ylabel("Torque (Ft-Lbs)");
hold off;

disp("Done!");